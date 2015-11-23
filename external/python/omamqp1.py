#!/usr/bin/env python

"""An external output module for sending log messages to an AMQP 1.0 message
   bus.

   Copyright (C) 2015 by Kenneth Giusti

   Licensed to the Apache Software Foundation (ASF) under one
   or more contributor license agreements.  See the NOTICE file
   distributed with this work for additional information
   regarding copyright ownership.  The ASF licenses this file
   to you under the Apache License, Version 2.0 (the
   "License"); you may not use this file except in compliance
   with the License.  You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing,
   software distributed under the License is distributed on an
   "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
   KIND, either express or implied.  See the License for the
   specific language governing permissions and limitations
   under the License.

"""

import logging
import optparse
import os
import select
import sys
import threading
try:
    import Queue
except:
    import queue as Queue

# This plugin relies on the QPID Proton python client API
# Available at https://pypi.python.org/pypi/python-qpid-proton
from proton import Message, LinkException, SessionException, Url
from proton import ConnectionException, TransportException
from proton.handlers import MessagingHandler
from proton.reactor import Container, ApplicationEvent, EventInjector

VERSION="0.0.0"

class MessageBusHandler(MessagingHandler):
    """Runs the Proton Message Handler in a dedicated thread.  Messages to be
    sent to the message bus are made available to the thread via the in_queue.
    """
    def __init__(self, urls, target, in_queue, injector, **conn_args):
        super(MessageBusHandler, self).__init__(auto_settle=True)
        self.exception = None
        self._urls = urls
        self._connection_args = conn_args
        self._target = target
        self._in_queue = in_queue
        self._injector = injector
        self._container = None
        self._running = True
        self._thread = threading.Thread(target=self._msg_loop)
        self._thread.name = "Message Bus I/O Thread"
        self._thread.daemon = True
        self._thread.start()

    def _msg_loop(self):
        try:
            container = Container(self)
            # periodically exit process() to check _running
            container.timeout = 1.0
            container.start()
            while self._running:
                if not container.process():
                    break
            container.stop()
        except Exception as e:
            self.exception = e
            raise

    def _connect(self):
        self._connection_args['urls'] = self._urls
        self._connection = self._container.connect(**self._connection_args)
        self._sender = self._container.create_sender(self._connection,
                                                     target=self._target,
                                                     name="rsyslog-omamqp1")

    def _send(self):
        # pull messages off the queue and send them
        count = 0
        while self._sender.credit and not self._in_queue.empty():
            msg = self._in_queue.get(False)
            self._sender.send(msg)
            count += 1
        if count:
            logging.debug("%s messages sent", count)

    def on_start(self, event):
        self._container = event.container
        self._container.selectable(self._injector)
        self._connect()

    def on_messages_available(self, event):
        """Application event indicating messages are ready to be fetched from
        the queue.
        """
        logging.debug("on_messages_available called")
        self._send()

    def on_shutdown(self, event):
        """Shutdown the Messaging Bus thread
        """
        logging.debug("on_shutdown called")
        self._running = False

    def on_sendable(self, event):
        logging.debug("on_sendable: %s" % str(event.sender))
        self._send()

    def on_transport_error(self, event):
        super(MessageBusHandler, self).on_transport_error(event)
        tport = event.transport
        if tport.condition and tport.condition.name in self.fatal_conditions:
            raise TransportException("error: %s" %
                                     str(event.transport.condition))
        logging.debug("Recoverable transport error: %s" % str(tport.condition))

    def on_connection_error(self, event):
        super(MessageBusHandler, self).on_connection_error(event)
        raise ConnectionException("error: %s" %
                                  str(event.connection.remote_condition))

    def on_session_error(self, event):
        super(MessageBusHandler, self).on_session_error(event)
        raise SessionException("error: %s" %
                               str(event.session.remote_condition))

    def on_link_error(self, event):
        super(MessageBusHandler, self).on_link_error(event)
        raise LinkException("error: %s" % str(event.link.remote_condition))

    def on_unhandled(self, name, event):
        logging.debug("Unhandled callback: %s: %s", name, event)


def _get_password(password_file):
    if not password_file:
        raise ValueError("password_file not provided")
    if password_file.startswith('pass:'):
        return password_file[5:]
    with open(password_file) as f:
        return f.read().strip(' \n\r')


msg_queue = Queue.Queue()
event_msgs = ApplicationEvent("messages_available")
event_die = ApplicationEvent("shutdown")
event_injector = EventInjector()
handler = None


def configFromFile():
    """Configuration is read from a file."""
    FILES = [os.path.expanduser("~/omamqp1.conf"),
             "/etc/rsyslog.d/omamqp1.conf"]
    ec = os.environ.get("RSYSLOG_OMAMQP1_CONF")
    if ec:
        FILES = [ec]+FILES

    opts = {}
    for f in FILES:
        try:
            with open(f, 'r') as fd:
                for line in fd:
                    line = line.strip(" \n\r")
                    if line and line[0] != '#':
                        key, value = line.split('=')
                        opts[key] = value
                break
        except:
            pass
    if not opts:
        raise RuntimeError("No configuration available")
    return opts


def configFromArgs():
    """Configuration is passed on the command line."""
    target = 'rsyslogd'
    parser = optparse.OptionParser(usage="usage: %prog [options] TARGET",
                                   description="Send rsyslog messages to"
                                   " TARGET (default '%s') via an AMQP1.0"
                                   " message bus.  Version %s"
                                   % (target, VERSION))
    parser.add_option("--url", default="amqp://localhost:5672",
                      help="address of message bus (default %default)."
                      " Also accepts a comma-separated list of addresses"
                      " which will be used for failover.")
    parser.add_option("--heartbeat", type="int", default=0,
                      help="A value in seconds indicating the desired"
                      " frequency of heartbeats used to test the underlying"
                      " socket is alive.")
    # TBD:
    #parser.add_option("--sasl-mechanisms",
    #                  help="A space-separated string of SASL mechanisms that"
    #                  " are allowed (whitelist). If not specified, the"
    #                  " defaults provided by the system are used.")
    parser.add_option("--username",
                      help="The username for SASL authentication (if"
                      " required).")
    parser.add_option("--password-file",
                      help="The path to a text file containing the password"
                      " used for SASL authentication (if required).  If the"
                      " value starts with the prefix 'pass:' then the"
                      " remaining text is used as the actual password. This"
                      " alternative is only meant to be used when security is"
                      " not necessary (eg. during development) as it will"
                      " allow the password to be visible to all users of the"
                      " system.")
    parser.add_option("--log-level", default="WARNING",
                      help="The default log level for internal logging")
    parser.add_option("--log-to-file", default="/dev/null",
                      help="Send internal log messages to a file.")

    o, args = parser.parse_args()
    opts = {}
    for k,v in vars(o).items():
        opts[k.replace('_','-')] = v
    opts['target'] = args[0] if args else target
    return opts


def onInit():
    global msg_queue
    global event_injector
    global handler

    opts = configFromArgs() if len(sys.argv) > 1 else configFromFile()

    # @TODO(kgiusti) - TBD:
    # ssl-ca-file
    # ssl-cert-file
    # ssl-key-file
    # ssl-password-file
    # sasl-disable

    log_level = opts.get('log-level', "WARNING").upper()
    level = {"DEBUG": logging.DEBUG,
             "INFO": logging.INFO,
             "WARNING": logging.WARNING,
             "ERROR": logging.ERROR,
             "CRITICAL": logging.CRITICAL}.get(log_level,
                                               "WARNING")
    log_to_file = opts.get('log-to-file', '/dev/null')
    logging.basicConfig(filename=log_to_file, level=level)

    urls = opts.get('url', "amqp://localhost:5672")
    urls = [u.strip(' ') for u in urls.split(',')]
    username = opts.get('username')
    if username:
        password = _get_password(opts.get("password-file"))
        urls = [str(Url(u,
                        username=username,
                        password=password))
                for u in urls]
    conn_args = {}
    heartbeat = opts.get('heartbeat')
    if heartbeat:
        conn_args['heartbeat'] = float(heartbeat)
    # sasl_mechs = opts.get('sasl-mechanisms')
    # if sasl_mechs:
    #     conn_args['allowed_mechs'] = sasl_mechs.upper()

    handler = MessageBusHandler(urls, opts.get('target', 'rsyslogd'),
                                msg_queue, event_injector, **conn_args)


def onExit():
    global event_injector
    global event_die
    global handler

    event_injector.trigger(event_die)
    handler._thread.join(timeout=30)
    if handler._thread.isAlive():
        logging.warning("Unable to kill Message Bus I/O thread")


def onReceive(msgs):
    """Put a list of strings (JSON log output) into a message and hand it over
    to the Message Bus thread.
    """
    global msg_queue
    global event_msgs
    global event_injector
    global handler

    # watchdog check to see if I/O thread is ok:
    if not handler._thread.isAlive():
        if handler.exception:
            raise handler.exception
        raise RuntimeError("message bus I/O thread unexpectedly died")

    pmsg = Message(body=msgs)
    msg_queue.put(pmsg)
    logging.debug("%s messages read", len(msgs))
    event_injector.trigger(event_msgs)


# main stdin loop, courtesy rsyslog:

maxAtOnce = 1024
pollPeriod = 0.75

onInit()
keepRunning = 1
while keepRunning == 1:
    while keepRunning and sys.stdin in select.select([sys.stdin], [], [],
                                                     pollPeriod)[0]:
        msgs = []
        msgsInBatch = 0
        while keepRunning and sys.stdin in select.select([sys.stdin], [], [],
                                                         0)[0]:
            line = sys.stdin.readline()
            if line:
                msgs.append(line.rstrip('\n\r'))
                msgsInBatch = msgsInBatch + 1
            else:
                # an empty line means stdin has been closed
                keepRunning = 0
            if msgsInBatch >= maxAtOnce:
                break
        if len(msgs) > 0:
            onReceive(msgs)
            sys.stdout.flush()  # very important, Python buffers far too much!
onExit()
