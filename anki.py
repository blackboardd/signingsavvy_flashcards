"""Module is used for establishing a connection to Anki

Establishes a connection to Anki via AnkiConnect and creates cards

Copyright (c) 2022 Brighten Tompkins

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""

try:
    import curses
except ImportError:
    print("Curses failed to import.")

import argparse
import json
import logging
import re
import threading
import urllib
from getpass import getpass
from logging import basicConfig
from os import path
from time import sleep
from types import SimpleNamespace
from typing import Any, Literal
from urllib.request import Request, urlopen

import requests
from signingsavvy import api

base = "http://127.0.0.1"
ssbase = "https://www.signingsavvy.com"
port = "5954"

import argparse
import getpass


class PasswordPromptAction(argparse.Action):
    def __init__(
        self,
        option_strings,
        dest=None,
        nargs=0,
        default=None,
        required=False,
        type=None,
        metavar=None,
        help=None,
    ):
        super(PasswordPromptAction, self).__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=nargs,
            default=default,
            required=required,
            metavar=metavar,
            type=type,
            help=help,
        )

    def __call__(self, parser, args, values, option_string=None):
        password = getpass.getpass()
        setattr(args, self.dest, password)


p = argparse.ArgumentParser(description="AnkiConnect and SigningSavvy")
p.add_argument("-u", dest="user", type=str)
p.add_argument("-p", dest="password", action=PasswordPromptAction, type=str)
p.add_argument("--hq", dest="hq", type=str, default="hd", help="ld, sd, or hd")

args = p.parse_args()

basicConfig(
    filename="signingsavvy_anki.log",
    format="[%(asctime)s] {%(pathname)s:%(lineno)d} \
%(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
    encoding="utf-8",
    level=logging.INFO,
)


def request(action, **params):
    return {"action": action, "params": params, "version": 6}


def invoke(action, **params):
    base = "http://localhost:8765"
    req = json.dumps(request(action, **params)).encode("utf-8")
    _open = urlopen(Request(base, req))

    res = json.load(_open)
    if len(res) != 2:
        raise Exception("Unexpected number of fields.")
    if "error" not in res:
        raise Exception("Missing required error field.")
    if "result" not in res:
        raise Exception("Missing required result field.")
    return res["result"]


dWords = "nonfiction::asl::words"
dSentences = "nonfiction::asl::sentences"


def addNote(options: dict, data: dict, deck: str, front: bool):
    logging.info(f"Adding {data['type']} note \
        as a {'front' if front else 'back'}...")
    logging.info(data)

    content = data["content"]
    extra = f"""
{data["extra"]}
<br />
Memory aid: {data["mind"]}
"""

    res = invoke(
        action="addNote",
        note={
            "deckName": deck,
            "modelName": "Basic",
            "fields": {
                "Front": content if front else "Video: ",
                "Back": extra if front else f"{content}<br /><br />{extra}",
            },
            "options": options,
            "tags": [
                f"asl::{data['type']}-id::{data['id']}",
                f"asl::{data['type']}-variant-id::{data['variantId']}",
            ],
            "video": [
                {
                    "url": data["video"],
                    "filename": f"{data['id']}{data['variantId']}.mp4",
                    "fields": ["Back" if front else "Front"],
                }
            ],
        },
    )

    logging.info(res)


def fetch(request: str):
    try:
        req = requests.get(request, headers={"user": args.user, "pass": args.password})

        # sleep to prevent server overload
        # sleep(2)

        return json.dumps(req.json())
    except:
        pass


def parse(data: str):
    return json.loads(data, object_hook=lambda d: SimpleNamespace(**d))


def addAllWords(options):
    logging.info("Adding all words.")

    initialWords = invoke(action="getTags")

    for _ in list("abcdefghijklmnopqrstuvwxyz"):
        results = parse(
            fetch(f"{base}:{port}/browse/{_}")
        ).signs.search_results

        for _ in results:
            id = re.findall(r"\d+$", _.uri)[0]
            if f"asl::word-id::{id}" in initialWords:
                continue

            info = parse(fetch(f"{base}:{port}/sign/{_.uri}"))

            for i in range(len(info.variants) - 1):
                variant = info.variants[i]
                usage = ""

                for _ in variant.usage:
                    try:
                        usage += f"English: {_.english}<br />"
                        usage += f"ASL: {_.asl}<br /><br />"
                    except:
                        usage += ""

                word = {
                    "id": f"{info.id}",
                    "variantId": f"{i +  1}",
                    "content": f"{info.name} ({info.clarification}) - {i + 1}",
                    "extra": f"Description: {variant.desc}<br /><br />Type: {variant.type}<br /><br />Usage:<br />{usage}",
                    "mind": variant.aid,
                    "type": "word",
                    "video": f"{ssbase}/media/mp4-{args.hq}/{variant.video}",
                }

                addNote(options, word, dWords, front=True)
                addNote(options, word, dWords, front=False)


def addAllSentences(options):
    logging.info("Adding all sentences.")

    categories = parse(fetch(f"{base}:{port}/sentences")).categories

    for _ in categories:
        results = parse(fetch(f"{base}:{port}/sentences/{_}")).categories

        for result in results:
            uri = result.uri.replace("sentences/", "")
            info = parse(fetch(f"{base}:{port}/sentence/{uri}"))
            gloss = "<br />"

            for _ in info.glossary:
                gloss += f"{_.id}: {_.name}<br />"

            if gloss == "<br />":
                gloss = ""

            sentence = {
                "id": f"{info.id}",
                "content": info.english,
                "extra": f"Category: {info.category}<br /><br />ASL: {info.asl}<br /><br />Glossary:<br />{gloss}",
                "mind": "",
                "type": "sentence",
                "video": f"{ssbase}/media/mp4-{args.hq}/{info.video}",
            }

            addNote(options, sentence, dSentences, front=True)
            addNote(options, sentence, dSentences, front=False)


def createDecks():
    deckNames = invoke("deckNames")
    for deck in [dWords, dSentences]:
        try:
            if deck in deckNames:
                raise FileExistsError

            logging.info(f"Creating {deck}")
            invoke("createDeck", deck=deck)
        except FileExistsError:
            logging.warning(f"Failed to create {deck}. Already exists.")


def deleteDecks():
    invoke("deleteDecks", decks=[dWords, dSentences])


def init():
    def options(deckName):
        return {
            "allowDuplicate": False,
            "duplicateScope": "deck",
            "duplicateScopeOptions": {
                "deckName": deckName,
                "checkChildren": False,
                "checkAllmodels": False,
            },
        }

    try:
        logging.info("Setting up local server for signingsavvy api...")
        threading.Thread(target=lambda: api.app.run(port=port)).start()

        logging.info("Creating decks...")
        createDecks()

        addAllWords(options(dWords))
        # addAllSentences(options(dSentences))
    except urllib.error.URLError:
        logging.error("Connection refused. Is Anki open and Anki Connect installed?")


init()
