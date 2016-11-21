#!/usr/bin/env python

import asyncore
import json

import click
import requests

import re

import html2text

from email.message import Message

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
    return msg.get_payload(0, True).as_string()
  else:
    return msg.get_payload(True)

Message.text = _msg_text

class SMTPError(Exception):
  def __init__(self, code, msg):
    self.code = code
    self.message = msg

  def __repr__(self):
    return '%d %s' % (self.code, self.message)


def forward_message(mailfrom, rcpttos, msg, webhook_url, authorization_token=None):
  if authorization_token and not authorization_token in msg.as_string():
    raise SMTPError(554, 'Rejecting message: missing or invalid authorization token')

  # fizz@buzz.com => fizz
  channel = re.search('^([^@]+)@.+$', rcpttos[0]).group(1)

  try:
    json_data = json.dumps({
      'username': mailfrom,
      'channel': ('#%s' % channel),
      'attachments': [
        {
            'title': msg['subject'],
            'text': html2text.html2text(msg.text()),
        }
      ]
    })
    echo (json_data)
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
