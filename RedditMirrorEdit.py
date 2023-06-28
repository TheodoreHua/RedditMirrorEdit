import argparse
import socket
from getpass import getpass
from hashlib import sha256
from itertools import zip_longest
from json import dump
from os import environ, mkdir
from os.path import isfile, isdir
from random import randint
from re import compile
from uuid import uuid4
from webbrowser import open as wbopen

import praw
import praw.models
from prawcore import OAuthException
from alive_progress import alive_bar
from dotenv import load_dotenv

EXPECTED = [
    "CLIENT_ID",
    "CLIENT_SECRET",
]
USER_MENTION_REGEX = compile(
    r"(^|\s)(<a href=\"/?u/[a-zA-Z0-9_-]+?\">/?u/[a-zA-Z0-9_-]+?</a>|/?u/[a-zA-Z0-9_-]+)"
)


def merge_iterators(*iterators):
    for i in zip_longest(*iterators, fillvalue=None):
        for j in i:
            if j is not None:
                yield j


def receive_code(state):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", 8000))
    server.listen(1)
    client = server.accept()[0]
    server.close()
    data = client.recv(1024).decode("utf-8")
    param_tokens = data.split(" ", 2)[1].split("?", 1)[1].split("&")
    params = {
        key: value for (key, value) in [token.split("=") for token in param_tokens]
    }
    if state != params["state"]:
        client.send(
            "HTTP/1.1 200 OK\r\n\r\nState Mismatch\nExpected {} Received: {}".format(
                state, params["state"]
            ).encode("utf-8")
        )
        client.close()
        return None
    elif "error" in params:
        client.send("HTTP/1.1 200 OK\r\n\r\n{}".format(params["error"]).encode("utf-8"))
        client.close()
        return None
    client.send(
        "HTTP/1.1 200 OK\r\n\r\nSuccess, you may close this window.".encode("utf-8")
    )
    client.close()
    return params["code"]


if __name__ == "__main__":
    # Configure argparse
    parser = argparse.ArgumentParser(
        description="Mass download and edit your Reddit comments"
    )
    parser.add_argument(
        "edit_text",
        type=str,
        help="What to replace your comments with. Valid placeholders are: '%{hash}', '%{id}' (without single quotes).",
    )
    parser.add_argument(
        "-w",
        "--whitelist",
        action="append",
        help="Whitelist any comments containing this string (case sensitive)",
    )
    parser.add_argument(
        "-wr",
        "--whitelist-regex",
        action="append",
        help="Whitelist any comments containing a match to this regex",
    )
    parser.add_argument(
        "-ws",
        "--whitelist-sub",
        action="append",
        help="Whitelist any comments in this subreddit (case insensitive)",
    )
    parser.add_argument(
        "--remove-mentions",
        action="store_true",
        help="Removes mentions of all usernames in comments",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt (this will NOT give you a chance to preview the comments that will be edited)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Store the comments in HTML format instead of Markdown",
    )
    parser.add_argument(
        "--map-save-interval",
        type=int,
        help="How often to save the map file (in comments). 0 to save at the end of all parsing. Default: 10",
        default=10,
    )
    parser.add_argument(
        "--edit-twice",
        action="store_true",
        help="Edit the comment twice for the theoretical singular backup Reddit keeps",
    )
    parser.add_argument(
        "--oauth",
        action="store_true",
        help="Use OAuth instead of username/password, needed for 2FA",
    )

    parse = parser.parse_args()

    # Load environment variables
    try:
        load_dotenv()
    except FileNotFoundError:
        pass

    if any(i not in environ or len(environ[i].strip()) == 0 for i in EXPECTED):
        print(
            "Missing one or more environment variables. Expected: {}".format(
                ", ".join(EXPECTED)
            )
        )
        exit()

    # Check for prerequisites
    if not isdir("jobs"):
        mkdir("jobs")

    JOB_ID = str(uuid4())

    try:
        if parse.oauth:
            reddit = praw.Reddit(
                client_id=environ["CLIENT_ID"],
                client_secret=environ["CLIENT_SECRET"],
                user_agent="RedditMirrorEdit Job {}".format(JOB_ID),
                redirect_uri="http://localhost:8000",
            )
            state = str(randint(0, 65000))
            url = reddit.auth.url(
                scopes=["read", "edit", "history", "identity"],
                state=state,
                duration="permanent",
            )
            wbopen(url)
            reddit.auth.authorize(receive_code(state))
        else:
            username = input("Username (wo/ u/ prefix): ").strip()
            password = getpass("Password: ")
            two_factor_code = input(
                "Enter your 2FA Code (if none, leave blank): "
            ).strip()
            if len(two_factor_code) > 0:
                password += ":" + two_factor_code
            reddit = praw.Reddit(
                client_id=environ["CLIENT_ID"],
                client_secret=environ["CLIENT_SECRET"],
                user_agent="RedditMirrorEdit Job {}".format(JOB_ID),
                username=username,
                password=password,
            )
            del password
        reddit.validate_on_submit = True
        me: praw.models.Redditor = reddit.user.me()
    except OAuthException as e:
        print("Invalid credentials. If you have 2FA enabled, you must use --oauth.")
        exit()

    MAP_FILE = "jobs/{}/map.json".format(JOB_ID)
    FILE_EXTENSION = ".html" if parse.html else ".md"
    mkdir("jobs/{}".format(JOB_ID))
    print("Job ID: {}".format(JOB_ID))

    # Initiate runtime variables
    map_dict = {}
    to_edit = {}
    comments_since_last_save = 0
    whitelist_strings = parse.whitelist if parse.whitelist else []
    whitelist_regexes = (
        [compile(i) for i in parse.whitelist_regex] if parse.whitelist_regex else []
    )
    whitelist_subs = (
        [i.lower() for i in parse.whitelist_sub] if parse.whitelist_sub else []
    )

    # Save all discovered comments
    with alive_bar(unknown="stars") as bar:
        for comment in merge_iterators(
            me.comments.controversial(limit=None),
            me.comments.hot(limit=None),
            me.comments.new(limit=None),
            me.comments.top(limit=None),
        ):
            try:
                comment: praw.models.Comment

                # Skips
                if comment.id in map_dict:
                    continue
                if comment.subreddit.display_name.lower() in whitelist_subs:
                    continue
                if any(i in comment.body for i in whitelist_strings):
                    continue
                if any(i.search(comment.body) for i in whitelist_regexes):
                    continue

                # Prerequisite Content
                body = comment.body_html if parse.html else comment.body
                if parse.remove_mentions:
                    body = USER_MENTION_REGEX.sub(" [USER MENTION REMOVED]", body)

                comment_hash = sha256(body.encode("utf-8")).hexdigest()
                filename = "jobs/{}/{}{}".format(JOB_ID, comment_hash, FILE_EXTENSION)

                # Save
                map_dict[comment.id] = comment_hash
                to_edit[comment.id] = comment
                if not isfile(filename):
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(body)

                # Save Map
                if comments_since_last_save != 0:
                    if comments_since_last_save >= parse.map_save_interval:
                        with open(MAP_FILE, "w", encoding="utf-8") as f:
                            dump(map_dict, f)
                        comments_since_last_save = 1
                    else:
                        comments_since_last_save += 1
            except (Exception,):
                try:
                    print(
                        "Error parsing comment {}, skipping - {}".format(
                            comment.id, comment.permalink
                        )
                    )
                except (Exception,):
                    print("Error parsing comment, skipping")

            # Progress Bar
            bar()

    # Save Map
    with open(MAP_FILE, "w", encoding="utf-8") as f:
        dump(map_dict, f)

    # Sanity Check
    if len(map_dict) != len(to_edit):
        print(
            "Sanity check failed, the number of comments in the map file ({}) does not match the number of comments to edit ({})".format(
                len(map_dict), len(to_edit)
            )
        )
        exit()

    # Confirmation
    if not parse.yes:
        num = len(to_edit)
        print(
            "Found {:,} ({:,} unique) comments to edit, to continue, enter the number of comments, 'n'/'N' to cancel.".format(
                num, len(set(map_dict.values()))
            )
        )
        print(
            "Note: It is recommended to view the comments that will be edited (by looking at the files in the jobs/{}/ directory) before continuing.".format(
                JOB_ID
            )
        )
        while True:
            inp = input().strip()
            if inp == str(num):
                break
            elif inp.lower() == "n":
                print("Exiting...")
                exit()
            else:
                print("Invalid input, try again.")

    # Edit
    with alive_bar(len(to_edit)) as bar:
        for comment_id, comment in to_edit.items():
            try:
                comment: praw.models.Comment

                # Prerequisite Content
                comment_hash = map_dict[comment_id]
                replacement_message = parse.edit_text.replace(
                    "%{hash}", comment_hash
                ).replace("%{id}", comment_id)

                # Edit
                if parse.edit_twice:
                    comment.edit(
                        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Sodales ut eu sem integer vitae justo eget magna fermentum."
                    )
                comment.edit(replacement_message)
            except (Exception,):
                try:
                    print(
                        "Error editing comment {}, skipping - {}".format(
                            comment.id, comment.permalink
                        )
                    )
                except (Exception,):
                    print("Error editing comment, skipping")

            # Progress Bar
            bar()

    # Done
    print(
        "Done! You can find the edited comments in the jobs/{}/ directory".format(
            JOB_ID
        )
    )
