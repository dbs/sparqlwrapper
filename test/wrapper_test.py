# -*- coding: utf-8 -*-
import inspect
import os
import sys

import logging
logging.basicConfig()

import unittest
from urlparse import urlparse
from urllib2 import Request
from cgi import parse_qs

# prefer local copy to the one which is installed
# hack from http://stackoverflow.com/a/6098238/280539
_top_level_path = os.path.realpath(os.path.abspath(os.path.join(
    os.path.split(inspect.getfile(inspect.currentframe()))[0],
    ".."
)))
if _top_level_path not in sys.path:
    sys.path.insert(0, _top_level_path)
# end of hack

from SPARQLWrapper import SPARQLWrapper, XML, GET, POST, JSON, JSONLD, N3, TURTLE, RDF, SELECT, INSERT
from SPARQLWrapper.Wrapper import QueryResult, QueryBadFormed, EndPointNotFound, EndPointInternalError


# we don't want to let Wrapper do real web-requests. so, we are…
# constructing a simple Mock!
from urllib2 import HTTPError
from StringIO import StringIO
import warnings

import SPARQLWrapper.Wrapper as _victim


class FakeResult(object):
    def __init__(self, request):
        self.request = request


def urlopener(request):
    return FakeResult(request)


def urlopener_error_generator(code):
    def urlopener_error(request):
        raise HTTPError(request.get_full_url, code, '', {}, StringIO(''))

    return urlopener_error
# DONE


class SPARQLWrapper_Test(unittest.TestCase):
    @staticmethod
    def _get_request(wrapper):
        request = wrapper.query().response.request  # possible due to mock above
        return request

    @staticmethod
    def _get_parameters_from_request(request):
        if request.get_method() == 'GET':
            pieces_str = urlparse(request.get_full_url()).query
        else:
            pieces_str = request.get_data()
        return parse_qs(pieces_str)

    @staticmethod
    def _get_request_parameters(wrapper):
        request = SPARQLWrapper_Test._get_request(wrapper)
        parameters = SPARQLWrapper_Test._get_parameters_from_request(request)

        return parameters

    def setUp(self):
        self.wrapper = SPARQLWrapper(endpoint='http://example.org/sparql/')
        _victim.urllib2.urlopen = urlopener

    def testConstructor(self):
        try:
            SPARQLWrapper()
            self.fail("SPARQLWrapper constructor should fail without arguments")
        except TypeError:
            pass

        wrapper = SPARQLWrapper(endpoint='http://example.org/sparql/')

        self.assertEqual(XML, wrapper.returnFormat, 'default return format is XML')
        self.assertTrue(
            wrapper.agent.startswith('sparqlwrapper'),
            'default user-agent should start with "sparqlwrapper"'
        )

        wrapper = SPARQLWrapper(endpoint='http://example.org/sparql/', returnFormat='wrongformat')
        self.assertEqual(XML, wrapper.returnFormat, 'default return format is XML')

        wrapper = SPARQLWrapper(endpoint='http://example.org/sparql/', defaultGraph='http://example.org/default')
        parameters = self._get_request_parameters(wrapper)
        self.assertEqual(
            ['http://example.org/default'],
            parameters.get('default-graph-uri'),
            'default graph is set'
        )

    def testReset(self):
        self.wrapper.setMethod(POST)
        self.wrapper.setQuery('CONSTRUCT WHERE {?a ?b ?c}')
        self.wrapper.setReturnFormat(N3)
        self.wrapper.addParameter('a', 'b')

        request = self._get_request(self.wrapper)
        parameters = self._get_parameters_from_request(request)

        self.assertEqual('POST', request.get_method())
        self.assertTrue(parameters['query'][0].startswith('CONSTRUCT'))
        self.assertTrue('rdf+n3' in request.get_header('Accept'))
        self.assertTrue('a' in parameters)

        self.wrapper.resetQuery()

        request = self._get_request(self.wrapper)
        parameters = self._get_parameters_from_request(request)

        self.assertEqual('GET', request.get_method())
        self.assertTrue(parameters['query'][0].startswith('SELECT'))
        self.assertFalse('rdf+n3' in request.get_header('Accept'))
        self.assertTrue('sparql-results+xml' in request.get_header('Accept'))
        self.assertFalse('a' in parameters)

    def testSetReturnFormat(self):
        self.wrapper.setReturnFormat('nonexistent format')
        self.assertEqual(XML, self.wrapper.query().requestedFormat)

        self.wrapper.setReturnFormat(JSON)
        self.assertEqual(JSON, self.wrapper.query().requestedFormat)

    def testAddParameter(self):
        self.assertFalse(self.wrapper.addParameter('query', 'dummy'))
        self.assertTrue(self.wrapper.addParameter('param1', 'value1'))
        self.assertTrue(self.wrapper.addParameter('param1', 'value2'))
        self.assertTrue(self.wrapper.addParameter('param2', 'value2'))

        pieces = self._get_request_parameters(self.wrapper)

        self.assertTrue('param1' in pieces)
        self.assertEqual(['value1', 'value2'], pieces['param1'])
        self.assertTrue('param2' in pieces)
        self.assertEqual(['value2'], pieces['param2'])
        self.assertNotEqual(['dummy'], 'query')

    def testSetCredentials(self):
        request = self._get_request(self.wrapper)
        self.assertFalse(request.has_header('Authorization'))

        self.wrapper.setCredentials('login', 'password')
        request = self._get_request(self.wrapper)
        self.assertTrue(request.has_header('Authorization'))
        # TODO: test for header-value using some external decoder implementation

    def testSetQuery(self):
        self.wrapper.setQuery('PREFIX example: <http://example.org/INSERT/> SELECT * WHERE {?s ?p ?v}')
        self.assertEqual(SELECT, self.wrapper.queryType)

        self.wrapper.setQuery('PREFIX e: <http://example.org/> INSERT {e:a e:b e:c}')
        self.assertEqual(INSERT, self.wrapper.queryType)

        self.wrapper.setQuery('UNKNOWN {e:a e:b e:c}')
        self.assertEqual(SELECT, self.wrapper.queryType, 'unknown queries result in SELECT')

    def testSetTimeout(self):
        self.wrapper.setTimeout(10)
        self.assertEqual(10, self.wrapper.timeout)

        self.wrapper.resetQuery()
        self.assertEqual(None, self.wrapper.timeout)

    def testClearParameter(self):
        self.wrapper.addParameter('param1', 'value1')
        self.wrapper.addParameter('param1', 'value2')
        self.wrapper.addParameter('param2', 'value2')

        self.assertFalse(self.wrapper.clearParameter('query'))
        self.assertTrue(self.wrapper.clearParameter('param1'))

        pieces = self._get_request_parameters(self.wrapper)

        self.assertFalse('param1' in pieces)
        self.assertTrue('param2' in pieces)
        self.assertEqual(['value2'], pieces['param2'])

        self.assertFalse(self.wrapper.clearParameter('param1'), 'already cleaned')

    def testSetMethod(self):
        self.wrapper.setMethod(POST)
        request = self._get_request(self.wrapper)

        self.assertEqual("POST", request.get_method())

        self.wrapper.setMethod(GET)
        request = self._get_request(self.wrapper)

        self.assertEqual("GET", request.get_method())

    def testIsSparqlUpdateRequest(self):
        self.wrapper.setQuery('DELETE WHERE {?s ?p ?o}')
        self.assertTrue(self.wrapper.isSparqlUpdateRequest())

        self.wrapper.setQuery("""
        PREFIX example: <http://example.org/SELECT/>
        BASE <http://example.org/SELECT>
        DELETE WHERE {?s ?p ?o}
        """)
        self.assertTrue(self.wrapper.isSparqlUpdateRequest())

    def testIsSparqlQueryRequest(self):
        self.wrapper.setQuery('SELECT * WHERE {?s ?p ?o}')
        self.assertTrue(self.wrapper.isSparqlQueryRequest())

        self.wrapper.setQuery("""
        PREFIX example: <http://example.org/DELETE/>
        BASE <http://example.org/MODIFY>
        ASK WHERE {?s ?p ?o}
        """)
        self.assertTrue(self.wrapper.isSparqlQueryRequest())

    def testQuery(self):
        qr = self.wrapper.query()
        self.assertTrue(isinstance(qr, QueryResult))

        request = qr.response.request  # possible due to mock above
        self.assertTrue(isinstance(request, Request))

        parameters = self._get_parameters_from_request(request)
        self.assertTrue('query' in parameters)
        self.assertTrue('update' not in parameters)

        self.wrapper.setQuery('PREFIX e: <http://example.org/> INSERT {e:a e:b e:c}')
        parameters = self._get_request_parameters(self.wrapper)
        self.assertTrue('update' in parameters)
        self.assertTrue('query' not in parameters)

        _victim.urllib2.urlopen = urlopener_error_generator(400)
        try:
            self.wrapper.query()
            self.fail('should have raised exception')
        except QueryBadFormed, e:
            #  TODO: check exception-format
            pass
        except:
            self.fail('got wrong exception')

        _victim.urllib2.urlopen = urlopener_error_generator(404)
        try:
            self.wrapper.query()
            self.fail('should have raised exception')
        except EndPointNotFound, e:
            #  TODO: check exception-format
            pass
        except:
            self.fail('got wrong exception')

        _victim.urllib2.urlopen = urlopener_error_generator(500)
        try:
            self.wrapper.query()
            self.fail('should have raised exception')
        except EndPointInternalError, e:
            #  TODO: check exception-format
            pass
        except:
            self.fail('got wrong exception')

        _victim.urllib2.urlopen = urlopener_error_generator(999)
        try:
            self.wrapper.query()
            self.fail('should have raised exception')
        except HTTPError, e:
            #  TODO: check exception-format
            pass
        except:
            self.fail('got wrong exception')

    def testQueryAndConvert(self):
        _oldQueryResult = _victim.QueryResult

        class FakeQueryResult(object):
            def __init__(self, result):
                pass

            def convert(self):
                return True

        try:
            _victim.QueryResult = FakeQueryResult
            result = self.wrapper.queryAndConvert()
            self.assertEqual(True, result)
        finally:
            _victim.QueryResult = _oldQueryResult


class QueryResult_Test(unittest.TestCase):
    def testConstructor(self):
        qr = QueryResult('result')
        self.assertEqual('result', qr.response)
        try:
            format = qr.requestedFormat
            self.fail('format is not supposed to be set')
        except:
            pass

        qr = QueryResult(('result', 'format'))
        self.assertEqual('result', qr.response)
        self.assertEqual('format', qr.requestedFormat)

    def testProxyingToResponse(self):
        class FakeResponse(object):
            def __init__(self):
                self.geturl_called = False
                self.info_called = False
                self.iter_called = False
                self.next_called = False

            def geturl(self):
                self.geturl_called = True

            def info(self):
                self.info_called = True
                return {"key": "value"}

            def __iter__(self):
                self.iter_called = True

            def next(self):
                self.next_called = True

        result = FakeResponse()

        qr = QueryResult(result)
        qr.geturl()
        qr.__iter__()
        qr.next()

        self.assertTrue(result.geturl_called)
        self.assertTrue(result.iter_called)
        self.assertTrue(result.next_called)

        info = qr.info()
        self.assertTrue(result.info_called)
        self.assertEqual('value', info.__getitem__('KEY'), 'keys should be case-insensitive')

    def testConvert(self):
        class FakeResponse(object):
            def __init__(self, content_type):
                self.content_type = content_type

            def info(self):
                return {"Content-type": self.content_type}

            def read(self, len):
                return ''

        def _mime_vs_type(mime, requested_type):
            """
            @param mime:
            @param requested_type:
            @return: number of warnings produced by combo
            """
            with warnings.catch_warnings(record=True) as w:
                qr = QueryResult((FakeResponse(mime), requested_type))

                try:
                    qr.convert()
                except:
                    pass

                return len(w)

        self.assertEqual(0, _mime_vs_type("application/sparql-results+xml", XML))
        self.assertEqual(0, _mime_vs_type("application/sparql-results+json", JSON))
        self.assertEqual(0, _mime_vs_type("text/n3", N3))
        self.assertEqual(0, _mime_vs_type("text/turtle", TURTLE))
        self.assertEqual(0, _mime_vs_type("application/ld+json", JSON))
        self.assertEqual(0, _mime_vs_type("application/ld+json", JSONLD))
        self.assertEqual(0, _mime_vs_type("application/rdf+xml", XML))
        self.assertEqual(0, _mime_vs_type("application/rdf+xml", RDF))

        self.assertEqual(1, _mime_vs_type("application/x-foo-bar", XML), "invalid mime")

        self.assertEqual(1, _mime_vs_type("application/sparql-results+xml", N3))
        self.assertEqual(1, _mime_vs_type("application/sparql-results+json", XML))
        self.assertEqual(1, _mime_vs_type("text/n3", JSON))
        self.assertEqual(1, _mime_vs_type("text/turtle", XML))
        self.assertEqual(1, _mime_vs_type("application/ld+json", XML))
        self.assertEqual(1, _mime_vs_type("application/ld+json", N3))
        self.assertEqual(1, _mime_vs_type("application/rdf+xml", JSON))
        self.assertEqual(1, _mime_vs_type("application/rdf+xml", N3))

if __name__ == "__main__":
    unittest.main()

