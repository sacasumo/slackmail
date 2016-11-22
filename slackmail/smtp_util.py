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


def _msg_text(msg):
  if msg.is_multipart():
    text = msg.get_payload(0, decode=True)
    return (text.as_string() if text is not None else '')
  else:
    text = msg.get_payload(decode=True)
    return (text if text is not None else '')

Message.text = _msg_text

class SMTPError(Exception):
  def __init__(self, code, msg):
    self.code = code
    self.message = msg

  def __repr__(self):
    return '%d %s' % (self.code, self.message)

# reduce multi-line title
def _reduce_title(title, append):
  decoded_title , encoding = append
  return title + decoded_title.decode(encoding if encoding is not None else 'utf-8')

def forward_message(mailfrom, rcptto, msg, webhook_url, authorization_token=None):
  if authorization_token and not authorization_token in msg.as_string():
    raise SMTPError(554, 'Rejecting message: missing or invalid authorization token')

  # fizz@buzz.com => fizz
  channel = re.search(r'^([^@]+)@.+$', rcptto).group(1)
  decoded_titles = decode_header(msg['subject'])
  title = reduce(_reduce_title, decode_header(msg['subject']), u'')
  formatted_text = html2text.html2text(msg.text().decode('utf-8'))
  # encode for slack
  encoded_text = re.sub(r'\n', "\\n", formatted_text)

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
