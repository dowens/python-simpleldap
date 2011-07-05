"""
This module makes simple LDAP queries simple.
"""

import ldap

from simpleldap.cidict import cidict


#
# Exceptions.
#

class SimpleLDAPException(Exception):
    """Base class for all simpleldap exceptions."""

class ObjectNotFound(SimpleLDAPException):
    """
    Exception when no objects were returned, but was expecting a single item.
    """

class MultipleObjectsFound(SimpleLDAPException):
    """
    Exception for when multiple objects were returned, but was expecting only
    a single item.
    """


class ConnectionException(Exception):
    """Base class for all Connection object exceptions."""

class InvalidEncryptionProtocol(ConnectionException):
    """Exception when given an unsupported encryption protocol."""

#
# Classes.
#

class LDAPItem(cidict):
    """
    A convenience class for wrapping standard LDAPResult objects.
    """

    def __init__(self, result):
        super(LDAPItem, self).__init__()
        self.dn, self.attributes = result
        # XXX: quick and dirty, should really proxy straight to the existing
        # self.attributes dict.
        for attribute, values in self.attributes.iteritems():
            # Make the entire list of values for each LDAP attribute
            # accessible through a dictionary mapping.
            self[attribute] = values

    def first(self, attribute):
        """
        Return the first value for the given LDAP attribute.
        """
        return self[attribute][0]

    def value_contains(self, value, attribute):
        """
        Determine if any of the items in the value list for the given
        attribute contain value.
        """
        for item in self[attribute]:
            if value in item:
                return True
        return False

    def __str__(self):
        """
        Print attribute names and values, one per line, in alphabetical order.

        Attribute names are displayed right-aligned to the length of the
        longest attribute name.
        """
        attributes = self.keys()
        longestKeyLength = max([len(attr) for attr in attributes])
        output = []
        for attr in sorted(attributes):
            values = ("\n%*s  " % (longestKeyLength, ' ')).join(self[attr])
            output.append("%*s: %s" % (longestKeyLength, attr, values))
        return "\n".join(output)


class Connection(object):
    """
    A connection to an LDAP server.
    """

    # The class to use for items returned in results.  Subclasses can change
    # this to a class of their liking.
    result_item_class = LDAPItem

    def __init__(self, hostname, port=None, dn='', password='',
                 encryption=None, require_cert=None, debug=False,
                 options=None):
        """
        Bind to hostname:port using the passed distinguished name (DN), as
        ``dn``, and password.

        If no user and password is given, try to connect anonymously with a
        blank DN and password.

        ``encryption`` should be one of ``'tls'``, ``'ssl'``, or ``None``.
        If ``'tls'``, then the standard port 389 is used by default and after
        binding, tls is started.  If ``'ssl'``, then port 636 is used by
        default.

        ``require_cert`` is None by default.  Set this to ``True`` or
        ``False`` to set the ``OPT_X_TLS_REQUIRE_CERT`` ldap option.

        If ``debug`` is ``True``, debug options are turned on within ldap and
        statements are ouput to standard error.  Default is ``False``.

        If give, ``options`` should be a dictionary of any additional
        connection-specific ldap  options to set, e.g.:
        ``{'OPT_TIMELIMIT': 3}``.
        """
        if not encryption or encryption == 'tls':
            protocol = 'ldap'
            if not port:
                port = 389
        elif encryption == 'ssl':
            protocol = 'ldaps'
            if not port:
                port = 636
        else:
            raise InvalidEncryptionProtocol(
                "Invalid encryption protocol, must be one of: 'tls' or 'ssl'.")

        if require_cert is not None:
            ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, require_cert)
        if debug:
            ldap.set_option(ldap.OPT_DEBUG_LEVEL, 255)
        else:
            ldap.set_option(ldap.OPT_DEBUG_LEVEL, 0)

        url='%s://%s:%s' % (protocol, hostname, port)
        self.connection = ldap.initialize(url)
        if options:
            for name, value in options.iteritems():
                self.connection.set_option(getattr(ldap, name), value)
        if encryption == 'tls':
            self.connection.start_tls_s()
        # It seems that python-ldap chokes when passed unicode objects with
        # non-ascii characters.  So if we have a unicode password, encode
        # it to utf-8.
        if isinstance(password, unicode):
            password = password.encode('utf-8')
        self.connection.simple_bind_s(dn, password)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        """
        Shutdown the connection.
        """
        self.connection.unbind_s()

    def search(self, filter, base_dn='', attrs=None, scope=ldap.SCOPE_SUBTREE,
               timeout=-1, limit=0):
        """
        Search the directory.
        """
        results = self.connection.search_ext_s(
            base_dn, scope, filter, attrs, timeout=timeout, sizelimit=limit)
        return self.to_items(results)

    def get(self, *args, **kwargs):
        """
        Get a single object.

        This is a convenience wrapper for the search method that checks that
        only one object was returned, and returns that single object instead
        of a list.  This method takes the exact same arguments as search.
        """
        results = self.search(*args, **kwargs)
        num_results = len(results)
        if num_results == 1:
            return results[0]
        if num_results > 1:
            raise MultipleObjectsFound()
        if num_results < 1:
            raise ObjectNotFound()

    def to_items(self, results):
        """
        Turn LDAPResult objects returned from the ldap library into more
        convenient objects.
        """
        return [self.result_item_class(item) for item in results]
