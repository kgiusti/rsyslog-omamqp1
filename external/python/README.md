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
configuration from a file called 'omamqp1.conf'.  The following
directories are searched in the following order to find this file:

* the value of the environment variable RSYSLOG_OMAMQP1_CONF
* the home directory of the current user
* the /etc/rsyslog.d/ directory

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
