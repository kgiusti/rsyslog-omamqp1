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

import sys
import select
import threading
try:
    import Queue
except:
    import queue as Queue

# This plugin relies on the QPID Proton python client API
# Available at https://pypi.python.org/pypi/python-qpid-proton
from proton import Message
from proton.handlers import MessagingHandler
from proton.reactor import Container, ApplicationEvent, EventInjector


class MessageBusHandler(MessagingHandler):
    def __init__(self, url, in_queue, injector):
        super(MessageBusHandler, self).__init__(auto_settle=True)
        self._url = url
        self._in_queue = in_queue
        self._injector = injector
        self._running = True
        self._thread = threading.Thread(target=self._msg_loop)
        self._thread.daemon = True
        self._thread.start()

    def _msg_loop(self):
        try:
            Container(self).run()
        except:
            print("EXCEPT?")
        print("EXIT")

    def _send(self):
        while self.sender.credit and not self._in_queue.empty():
            msg = self._in_queue.get(False)
            self.sender.send(msg)
            print("sent message")

    def on_start(self, event):
        print("ON_START %s" % str(event))
        self.container = event.container
        self.container.selectable(self._injector)
        self.sender = self.container.create_sender(self._url)

    def on_messages_available(self, event):
        # pull then off the queue and send them
        self._send()

    def on_sendable(self, event):
        # gabba gabba hey
        self._send()


    def on_connection_closed(self, event):
        """
        Called when the connection is closed.
        """
        print("on_connection_closed %s" % event)

    def on_session_closed(self, event):
        """
        Called when the session is closed.
        """
        print("on_session_closed %s" % event)

    def on_link_closed(self, event):
        """
        Called when the link is closed.
        """
        print("    def on_link_closed(self, event): %s" % event)
        
    def on_connection_closing(self, event):
        """
        Called when the peer initiates the closing of the connection.
        """
        print("    def on_connection_closing(self, event): %s" % event)
        
    def on_session_closing(self, event):
        """
        Called when the peer initiates the closing of the session.
        """
        print("    def on_session_closing(self, event): %s" % event)

    def on_link_closing(self, event):
        """
        Called when the peer initiates the closing of the link.
        """
        print("    def on_link_closing(self, event): %s" % event)

    def on_disconnected(self, event):
        """
        Called when the socket is disconnected.
        """
        print("    def on_disconnected(self, event): %s" % event)


    def on_accepted(self, event):
        """
        Called when the remote peer accepts an outgoing message.
        """
        print("    def on_accepted(self, event): %s" % event)
        

    def on_rejected(self, event):
        """
        Called when the remote peer rejects an outgoing message.
        """
        print("    def on_rejected(self, event): %s" % event)
        

    def on_released(self, event):
        """
        Called when the remote peer releases an outgoing message. Note
        that this may be in response to either the RELEASE or MODIFIED
        state as defined by the AMQP specification.
        """
        print("    def on_released(self, event): %s" % event)
        

    def on_settled(self, event):
        """
        Called when the remote peer has settled the outgoing
        message. This is the point at which it shouod never be
        retransmitted.
        """
        print("    def on_settled(self, event): %s" % event)
        
    def on_message(self, event):
        """
        Called when a message is received. The message itself can be
        obtained as a property on the event. For the purpose of
        refering to this message in further actions (e.g. if
        explicitly accepting it, the ``delivery`` should be used, also
        obtainable via a property on the event.
        """
        print("    def on_message(self, event): %s" % event)



# configs
URL=127.0.0.1:5672/amq.topic
maxAtOnce=1024
pollPeriod=0.75

msg_queue = Queue.Queue()
msg_event = ApplicationEvent("messages_available")
event_injector = EventInjector()

handler = MessageBusHandler(URL, msg_queue, event_injector)

def onInit():
    pass

def onExit():
    pass

def onReceive(msgs):
    global msg_queue
    global msg_event
    global event_injector

    pmsg = Message(body=msgs)
    msg_queue.put(pmsg)
    event_injector.trigger(msg_event)



# main stdin loop, courtesy rsyslog:
onInit()
keepRunning = 1
while keepRunning == 1:
	while keepRunning and sys.stdin in select.select([sys.stdin], [], [], pollPeriod)[0]:
		msgs = []
	        msgsInBatch = 0
		while keepRunning and sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
			line = sys.stdin.readline()
			if line:
				msgs.append(line)
			else: # an empty line means stdin has been closed
				keepRunning = 0
			msgsInBatch = msgsInBatch + 1
			if msgsInBatch >= maxAtOnce:
				break;
		if len(msgs) > 0:
			onReceive(msgs)
			sys.stdout.flush() # very important, Python buffers far too much!
onExit()
