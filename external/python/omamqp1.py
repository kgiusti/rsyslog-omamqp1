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
    """Runs the Proton Message Handler in a dedicated thread.  Messages to be
    sent to the message bus are made available to the thread via the in_queue.
    """
    def __init__(self, url, in_queue, injector):
        super(MessageBusHandler, self).__init__(auto_settle=True)
        self._url = url
        self._in_queue = in_queue
        self._injector = injector
        self._container = None
        self._running = True
        self._thread = threading.Thread(target=self._msg_loop)
        self._thread.daemon = True
        self._thread.start()

    def _msg_loop(self):
        try:
            container = Container(self)
            container.timeout = 3.0
            container.start()
            while self._running:
                if not container.process():
                    break
            print("Stopping...")
            container.stop()
        except Exception as e:
            print("EXCEPT? %s" % str(e))
        print("EXIT")

    def _send(self):
        # pull messages off the queue and send them
        print("sending messages")
        while self.sender.credit and not self._in_queue.empty():
            msg = self._in_queue.get(False)
            self.sender.send(msg)
        print("messages sent")

    def on_start(self, event):
        print("ON_START %s" % str(event))
        self._container = event.container
        self._container.selectable(self._injector)
        self.sender = self._container.create_sender(self._url, name="rsyslog-client")

    def on_messages_available(self, event):
        """Application event indicating messages are ready to be fetched from
        the queue.
        """
        self._send()

    def on_shutdown(self, event):
        """Shutdown the Messaging Bus thread
        """
        print("Shutting down Message Bus thread")
        self._running = False

    def on_sendable(self, event):
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
URL="127.0.0.1:5672/KEN"
maxAtOnce=1024
pollPeriod=0.75

msg_queue = Queue.Queue()
event_msgs = ApplicationEvent("messages_available")
event_die = ApplicationEvent("shutdown")
event_injector = EventInjector()

handler = MessageBusHandler(URL, msg_queue, event_injector)

def onInit():
    pass

def onExit():
    global event_injector
    global event_die

    event_injector.trigger(event_die)
    handler._thread.join(timeout=30)
    if handler._thread.isAlive():
        # just warn - we're shutting down anyhow
        print("Message Bus thread failed to shutdown")

def onReceive(msgs):
    """Put a list of strings (JSON log output) into a message and hand it over
    to the Message Bus thread.
    """
    global msg_queue
    global event_msgs
    global event_injector

    pmsg = Message(body=msgs)
    msg_queue.put(pmsg)
    event_injector.trigger(event_msgs)



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
