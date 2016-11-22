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

def _reduce_message_texts(text, append):
  maybeText = append.get_payload(decode=True)
  encoding = append.get_content_charset('utf-8')
  return text + (u'\n' + maybeText.decode(encoding) if maybeText is not None else u'')

def _msg_text(msg):
  if msg.is_multipart():
    text_payloads = filter(lambda msg: msg.get_content_maintype() == 'text', msg.get_payload())
    return reduce(_reduce_message_texts, text_payloads, u'')
  else:
    text = msg.get_payload(decode=True)
    encoding = msg.get_content_charset('utf-8')
    return (text.decode(encoding) if text is not None else u'')

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
  formatted_text = html2text.html2text(msg.text())
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
