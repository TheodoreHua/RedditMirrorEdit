# Reddit Mirror Edit
[![Semi-Maintained](https://img.shields.io/badge/Maintenance%20Level-Semi--Maintained-yellowgreen.svg)](https://github.com/TheodoreHua/MaintenanceLevels#semi-maintained)

This is a tool designed to meet my own needs, which allows for the mass editing of Reddit comments,
while also creating a copy of your comments locally, and editing the comments with a link to (your own) site where you
can choose to host the comments yourself. This allows for the removal of your data, without causing a detriment
to the actual community.

This program isn't extremely polished, as it was originally designed for my own use. I've decided to release it in case
anyone else finds it useful. If you have any issues, feel free to open an issue, or submit a pull request.

## How does it work?
The tool attempts to find all of your comments on Reddit (using different sorts, and running multiple times), gets the
content of the comments, stores a copy of the comments locally, and then edits the comment with your own text.

## How are the comments stored?
To prevent a bunch of duplicate comments from wasting space, all comments are stored in flat files (MD or HTML files),
with the name being a SHA-256 hash of the comment's content. If another comment exists with the same content, it will
not be stored again. This comes with the inherent risk of hash collisions, but the risk is low enough for my purposes.

A main JSON file is also created, which contains all comment's IDs, and the corresponding SHA-256 hash of the comment's
content. This can be used if you intend of parsing the data in another program or in some other way.

## Frequently Asked Questions
### Does this work with submissions?
Not at the moment, I made this for personal use, and I don't have many submissions. You are free to fork and add 
submission support yourself.

### How can I host my comments?
The program supports you editing your comments with anything you like, including allowing placeholders for the comment
ID and/or the comment's hash. This should work for most configurations. You can also choose to create your own dynamic
site that contains a search function (in which case just link to the main page and don't use any placeholder).
For my uses, I am hosting all comments on an S3 instance, in their hashed filename, HTML form. All comments are then
edited to contain a link to the S3 instance, using the hash placeholder to link to the correct comment.

### Will this get every comment?
Unfortunately, Reddit only allows you to get your past 1000 comments. Although this tool attempts to get more by
using different sorting patterns (which may show additional comments), it is not guaranteed to get all of them.

You can request a copy of your data from Reddit, which should include all of your comments. ~~This would in theory
allow you to use this tool to get everything, but I am still waiting on my data request at the time of writing this,
so the feature is not yet implemented. It will be added in the future.~~ This feature has now been added, and can
be used using the `--csv` parameter.

### I'm running this program again, how do I make sure it doesn't get my already edited comments?
Pass in as much as your edit text as you can into the string whitelist. The functionality for passing in a JSON
file of comment IDs to ignore is not yet implemented, but may be in the future.
