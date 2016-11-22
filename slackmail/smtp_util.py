#!/usr/bin/env python

import asyncore
import json

import click
import requests

import re

import html2text

from email.message import Message
from email.header import decode_header

def echo(msg, fg=None):
  if not fg:
    click.echo(msg)
  else:
    click.echo(click.style(msg, fg=fg))

def warn(msg):
  return echo(msg, fg='yellow')

def error(msg):
  return echo(msg, fg='red')

def _md_to_slack_format(str):
  # [](url "title" ) => <url|title>
  str = re.sub(r'\[\]\((\S+)\s*"([^"]+)"\s*\)', r'<\1|\2>', str)
  # [text](url) => <url|text>
  str = re.sub(r'\[([^\]]+)\]\((\S+)\s*\)', r'<\2|\1>', str)
  # [text](url "title" ) => <url|text>
  str = re.sub(r'\[([^\]]+)\]\((\S+)\s*"([^"]+)"\s*\)', r'<\2|\1>', str)
  return str

def _remove_line_break(str):
  return re.sub(r'(\r|\n|\r\n)', '', str)

def _html_parser():
  parser = html2text.HTML2Text()
  # https://github.com/Alir3z4/html2text/blob/master/docs/usage.md#available-options
  parser.body_width = 0
  parser.ignore_images = True
  parser.ignore_anchors = True
  parser.ignore_tables = True
  parser.skip_internal_links = True
  parser.inline_links = True
  parser.single_line_break = True
  parser.re_space = True
  return parser

# DO NOT PASS MULTIPART MESSAGE !
def _message_to_text(msg):
  encoding = msg.get_content_charset('utf-8')
  if msg.get_content_maintype() == 'text':
    if msg.get_content_subtype() == 'plain':
      maybe_text = msg.get_payload(decode=True)
      return (maybe_text.decode(encoding) if maybe_text is not None else None)
    else: # e.g. text/html
      text = msg.get_payload(decode=True)
      if text is None:
        return None

      normalized_html = _remove_line_break(text.decode(encoding))

      return _md_to_slack_format(_html_parser().handle(normalized_html))

  else: # e.g. image/png
    return None

def _reduce_message_texts(text, append):
  maybe_text = _message_to_text(append)
  return text + (u'\n' + maybe_text if maybe_text is not None else u'')

def _msg_text(msg):
  if msg.is_multipart():
    text_payloads = filter(lambda m: m.get_content_maintype() == 'text', msg.get_payload())
    return reduce(_reduce_message_texts, text_payloads, u'')
  else:
    maybe_text = _message_to_text(msg)
    return (maybe_text if maybe_text is not None else u'')

Message.text = _msg_text

class SMTPError(Exception):
  def __init__(self, code, msg):
    self.code = code
    self.message = msg

  def __repr__(self):
    return '%d %s' % (self.code, self.message)

# reduce multi-line header and decode
def _reduce_encoded_header(title, append):
  decoded_title , encoding = append
  return title + decoded_title.decode(encoding if encoding is not None else 'utf-8')

def forward_message(mailfrom, rcptto, msg, webhook_url, authorization_token=None):
  if authorization_token and not authorization_token in msg.as_string():
    raise SMTPError(554, 'Rejecting message: missing or invalid authorization token')

  # fizz@buzz.com => fizz
  channel = re.search(r'^([^@]+)@.+$', rcptto).group(1)
  decoded_titles = decode_header(msg['subject'])
  title = reduce(_reduce_encoded_header, decode_header(msg['subject']), u'')
  text = msg.text()
  # encode for slack
  encoded_text = re.sub(r'\n', "\\n", text)

  try:
    json_data = json.dumps({
      'username': mailfrom,
      'channel': ('#%s' % channel),
      'attachments': [
        {
            'title': title,
            'text': encoded_text,
        }
      ]
    })
    echo(json_data, fg='white')
    r = requests.post(webhook_url, data=json_data)
    r.raise_for_status()
  except Exception, e:
    error('Slack reported an error: %s' % e)
    raise SMTPError(554, 'Error posting to webhook')


def run_server(server):
  echo('Starting SMTP server on %s' % (server._localaddr,), fg='green')
  try:
    asyncore.loop()
  except KeyboardInterrupt:
    pass
