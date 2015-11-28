# omamqp1.py #

omamqp1.py is an external rsyslog output module plugin.

This plugin can be integrated into rsyslog in two different ways. For
rsyslog versions < 8.0.0, omamqp1.py can be run via the [omprog output
module](http://www.rsyslog.com/doc/omprog.html) that is included in rsyslog.

rsyslog versions 8.0.0 and later may also use the omprog output
modules, but it is also able to [invoke the plugin
directly.](http://www.rsyslog.com/writing-external-output-plugins-for-rsyslog/)

This plugin requires the Apache QPID Proton python library, version
0.10+.  This should be installed on the system that is running
rsyslogd.


## Message Format ##

Messages sent from omamqp1.py to the message bus contain a list of
strings.  Each string is a separate log message.  The list is ordered
such that the oldest log appears at the front of the list, whilst the
most recent log is at the end of the list.


## Configuration ##

### omprog ###

To use this plugin via omprog, you must configure rsyslog to load the
omprog module and define an action for it.  The action must include an
argument called _binary_ that is set to the path to the omamqp1.py
plugin file.

Example:

    module(load="omprog")
    action(type="omprog"
           binary="/<path to>/omamqp1.py"
           template="RSYSLOG_TraditionalFileFormat")

In this case, the omamqp1.py program will attempt to read its
configuration from a file.  The following paths are searched in order
to find this file:

* the value of the environment variable RSYSLOG_OMAMQP1_CONF
  - e.g. export RSYSLOG_OMAMQP1_CONF=/root/omamqp1.conf
* the home directory of the current user
  - e.g. /home/user/omamqp1.py
* the file /etc/omamqp1.conf

The format of the file is a list of 'name=value' pairs.  Only one
name/value pair is allow per line.  Lines starting with the '#'
character and blank lines are ignored.  See the [sample omamqp1.conf
configuration file](./omamqp1.conf) for details.

#### Command Line ####

Versions of rsyslog >= 7.5.1 allow arguments to be passed to the
omamqp1.py program.

Example:

    module(load="omprog")
    action(type="omprog"
           binary="/<path to>/omamqp1.py <args> <target>"
           template="RSYSLOG_TraditionalFileFormat")

The format of the omamqp1.py command line:

    omamqp1.py <options...> [target]

Use the --help option to list all the available options.  omamqp1.py
takes one argument: a _target_.  The target is the address that is used
as the destination for all messages.  If not specified, a default
target of 'rsyslogd' is used.

For example, to send all messages to a queue call "log-queue" on a
broker running on myhost.com:

    omamqp1.py --url amqp://myhost.com log-queue

### via rsyslog external plugin interface ###

TBD

### SASL Configuration ###

omamqp1.py uses Cyrus SASL to authenticate itself with the message
bus.  Be sure the omamqp1.py configuration is properly set up for
authentication with the message bus via SASL.  For example, if
authentication requires username and password credentials, be sure
these parameters are set in the omamqp1.conf configuration file.  If
authentication is not required, the message bus should allow clients
to use the ANONYMOUS mechanism.

## Broker Configuration ##

### qpidd ###

To use the Apache QPID C++ broker _qpidd_ as the message bus, a
version of qpidd that supports the AMQP 1.0 protocol must be used.
AMQP 1.0 has been available in qpidd since release 0.26.

The destination for message (target) must be created before log
messages arrive.  This can be done using the qpid-config tool.

Example:

    qpid-config add queue rsyslogd

Alternatively, the target can be created on demand by configuring a
queue-pattern (or topic-pattern) that matches the target.  To do this,
add a _queue-patterns_ (or _topic_patterns_) directive to the qpidd
configuration file /etc/qpid/qpidd.conf.

For example, to have qpidd automatically create a queue named
_rsyslogd_, add the following to the qpidd configuration file:

    queue-patterns=rsyslogd

or, if a topic is desired instead of a queue:

    topic-patterns=rsyslogd

These dynamic targets are auto-delete and will be destroyed once there
are no longer any subscribers or queue-bound messages.

Versions of qpidd <= 0.34 also need to have the SASL service name set
to 'amqp'. Add this to the qpidd.conf file:

    sasl-service-name=amqp

### qdrouterd standalone ###

This output module may be used with the _QPID Dispatch_ router
(qdrouterd) as the message bus.

The default qdrouterd configuration does not hav SASL authentication
turned on.  You must set up SASL in the qdrouter configuration file
/etc/qpid-dispatch/qdrouterd.conf

First create a SASL configuration file for qdrouterd.  This
configuration file is usually /etc/sasl2/qdrouterd.conf, but its
default location may vary depending on your platform's configuration.

This document assumes you understand how to properly configure SASL.

Here is an example qdrouterd SASL configuration file that allows the
client to use the DIGEST-MD5 or PLAIN authentication mechanisims, plus
a SASL user database:

    pwcheck_method: auxprop
    auxprop_plugin: sasldb
    sasldb_path: /var/lib/qdrouterd/qdrouterd.sasldb
    mech_list: DIGEST-MD5 PLAIN

Once a SASL configuration file has been set up for qdrouterd the path
to the directory holding the configuration file and the basename of
the configuration file (sas '.conf') must be added to the
/etc/qpid-dispatch/qdrouterd.conf configuration file.  This is done by
adding _saslConfigPath_ and _saslConfigName_ to the _container_
section of the configuration file. For example, assuming the file
/etc/sasl2/qdrouter.conf holds the qdrouterd SASL configuration:

    container {
        workerThreads: 4
        containerName: Qpid.Dispatch.Router.A
        saslConfigPath: /etc/sasl2
        saslConfigName: qdrouterd
    }

In addition, the address used by the omamqp1.py plugin to connect to
qdrouterd must have SASL authentication turned on.  This is done by
adding the _authenticatePeer_ attribute set to 'yes' to the
corresponding _listener_ entry:

    listener {
        addr: 0.0.0.0
        port: amqp
        authenticatePeer: yes 
    }

This should complete the SASL setup needed by qdrouterd.

The target address used as the destination for the log messages must
be picked with care.  qdrouterd uses the prefix of the target address
to determine the forwarding pattern used for messages sent using that
target address.  Addresses starting with the prefix _unicast_ are
distributed to only one message receiver.  If there are multiple
message consumers listening to that target address, only one listener
will receive the message.  In this case, qdrouterd will load balance
messages across the multiple listeners - much like a queue with
competing subscribers.  For example:

    omamqp1.py --url amqp://qdrouterd.myhost.com unicast/log-queue

If a multicast pattern is desired - where all active listeners receive
their own copy of the message - the target address prefix _multicast_
may be used.  For example:

    omamqp1.py --url amqp://qdrouterd.myhost.com multicast/log-queue

Note well: if there are _no_ active receivers for the log messages,
messages will be rejected the qdrouterd.  Currently omamqp1.py drops
rejected messages.

### qdrouterd in combination with qpidd ###

A qdrouterd-based message bus can use a broker as a message storage
mechanism for those that require broker-based message services (such
as a message store).  This section explains how to configure qdrouterd
for this type of deployment.  Please read the qdrouterd standalone
description above first, as the SASL configuration requirements are
explained there.

Each qdrouterd instance that is to connect the broker to the message
bus must define a _connector_ section in the qdrouterd.conf file.
This connector contains the addressing information necessary to have
the message bus set up a connection to the broker.  For example, if a
broker is available on host broker.host.com at port 5672:

    connector {
        name: mybroker
        role: on-demand
        addr: broker.host.com
        port: 5672
    }

In order to route messages to and from the broker, a static link route
must be configured.  This link route contains a target address prefix
and the name of the connector to use for forwarding matching messages.

For example, to forward messages that have a target address prefixed
by 'Broker' to the connector defined above, the following link
pattern must be added to the qdrouterd.conf configuration:

    linkRoutePattern {
        prefix: /Broker/
        connector: mybroker
    }

A queue must then be created on the broker.  The name of the queue
must be prefixed by the same prefix specified in the linkRoutePattern
entry.  For example:

    $ qpid-config add queue Broker/rsyslogd

Lastly, use the name of the queue for the target address used by
omamqp1.py:


    omamqp1.py --url amqp://qdrouterd.myhost.com Broker/rsyslogd

## Debugging ##

I found debugging this module very difficult.  I do not
have much experience with rsyslogd debugging in general, so I am
ignorant in the methods used to debug external modules.

Couple of tips:

* Use the _log-to-file_ and _log-level_ options to gather logs from
  omamqp1.py
* Test your configuration outside of rsyslog.  omamqpy1.py can be run
  directly from the command line.  It will run exactly the same way it
  does under rsyslogd, so any configuration issues and bugs should be
  reproducible.  Anything you type at the command line will be sent as
  a message to the message bus once you hit enter.  I highly recommend
  you try this method first before you deploy rsyslogd, since it will
  uncover connection issues (such as authentication failures) that are
  hard to diagnose from within rsyslogd. Use the _simple_recv.py_
  python example client from the proton project as a test message
  consumer.  See
  https://github.com/apache/qpid-proton/blob/master/examples/python/simple_recv.py
* (Advanced) Set the environmental variable "PN_TRACE_FRM" to 1 before
  invoking omamqp1.py on the command line.  This will print a low
  level protocol trace to stdout. Do *not* do this when running as a
  module within rsyslogd. If you do, you're gonna have a bad time.  If
  the trace does not show an obvious issue, feel free to post a
  question on users@qpid.apache.org.  If possible include the trace
  (inline, attachments are stripped by the mail server).

### Example ###

Assuming a qdrouterd is running standalone on the local machine.  It's
SASL configuration contains the credentials for a user named _guest_
with password _nopassword_.

First, run the simple_recv.py client.  This should be done in a
separate terminal so the output can be viewed:

    $ ./simple_recv.py -a guest:nopassword@127.0.0.1:5672/unicast/rsyslogd

While simple_recv.py is running, invoke omamqp1.py on the command line:

    $ ./omamqp1.py --url amqp://127.0.0.1:5672 --username guest --password-file pass:nopassword unicast/rsyslogd

omamqp1.py will wait for input.  Enter a few lines of text, hitting *Enter* after each line.

    Hi There.
    This is a message.

If everything is working, the following will appear on the simple_recv.py stdout:

    ['Hi There.']
    ['This is a message.']

To exit omamqpy1.py, hit Control-D.
