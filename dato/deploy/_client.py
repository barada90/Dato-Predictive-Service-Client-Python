"""
This module defines PredictiveServiceClient that consumes service provided
by Dato Predictive Service.
"""

import os
import json
import urllib
import logging
import requests
from ConfigParser import ConfigParser
from requests.auth import HTTPBasicAuth

SERVICE_INFO_SECTION_NAME = "Service Info"

class NonExistError(Exception):
    pass

class PredictiveServiceClient(object):
    def __init__(self, endpoint = None, api_key = None, should_verify_certificate = None, config_file = None):
        '''Constructs a new PredictiveServiceClient

        PredictiveServiceClient may be instantiated in one of the following two ways:

        a. Pass endpoint/api_key/should_verify_certificate to the constructor

            >>> client = PredictiveServiceClient(
                    endpoint = <endpoint>,
                    api_key = <api_key>,
                    should_verify_certificate = <True-or-False>)

        b. Create a configuration file and use the configuration file to instantiate
        the PredictiveServiceClient

            >>> client = PredictiveServiceClient(config_file = <path_to_file>)

        The configuration file is expected to be in a format that is similar to
        Microsoft Windows INI file and can be consumed by python package
        ConfigParser, it consists multipe sections and a list of key/value pairs
        inside each section, this is a sample file:

        [Service Info]
        endpoint = http://service-dns-name
        api key = api-key-string
        verify certificate = False

        Parameters
        -----------

        endpoint : str
            The Predictive Service endpoint to connect to, for example:
            https://myservice.mycompany.com

        api_key : str
            The API key for accessing your Predictive Service.

        should_verify_certificate: boolean
            Whether or not to very your server's certificate. If your Predictive
            Service is launched with a self-signed certificate or without certificate,
            should_verify_certificate needs to be False, otherwise True.

        config_file : str
            Path to the file where configuration file is stored. The config file
            is normally generated by your Predictive Service administrator through
            the following command:
                deployment.save_client_config(
                        file_path = <path-to-file>,
                        predictive_service_cname = <http://myservice.mycompany.com> )

        '''
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("Predictive Client")

        if config_file:
            self._read_config(config_file)
        else:
            if not endpoint or not api_key:
                raise ValueError("Either 'config_file' or ('endpoint' and 'api_key') pair need to be provided to initialize PredictiveServiceClient.")

            self.endpoint = endpoint
            self.api_key = api_key
            self.should_verify_certificate = should_verify_certificate or False

        self.query_timeout = 10
        try:
            res = self._ping()
            self._schema_version = json.loads(res).get('schema_version',-1)
        except Exception as e:
            self._schema_version = -1

    def __str__(self):
        '''String representation of the PredictiveServiceClient'''
        s = ""
        s += 'Predictive Service Client:\n'
        s += "\tendpoint: %s\n" % self.endpoint
        return s

    def __repr__(self):
        '''String representation of the PredictiveServiceClient'''
        return self.__str__()

    def set_query_timeout(self, timeout = 10):
        '''
        Set query timeout in seconds

        Parameters
        -----------
        timeout : int
            The timeout (in seconds) of the query to the Predictive Service.

        Examples
        ---------

            >>> deployment.set_query_timeout(30)

        '''
        if timeout <= 0 or not isinstance(timeout, int):
            raise ValueError('"timeout" value has to be a positive integer in seconds.')

        self.query_timeout = timeout

    def query(self, uri, **kwargs):
        '''Query a Predictive Service object

        Parameters
        ----------
        uri : str
            The model uri, must have been deployed in server side

        kwargs : kwargs
            The keyword arguments passed into query method

        Examples
        --------

            >>> client = PredictiveServiceClient(config_file='some file')

            To predict a preference score for a product for a particular user:

            >>> data = {'dataset':{'user_id':175343, 'product_id':1011}}
            >>> client.query('recommender', method = 'predict', data = data)

            To predict preference scores for a list of user-product pairs:

            >>> data = {'dataset':[
                {'user_id':175343, 'product_id':1011},
                {'user_id':175344, 'product_id':1012}
                ]}
            >>> client.query('recommender', method='predict', data=data)

            To predictive preference scores:

            >>> client.query('recommender', method='predict', data=data)

        Returns
        -------
        out : dict
            Returns the query result.  If successful, the actual query result will
            be in result['response']

        '''
        if not isinstance(uri, basestring):
            raise TypeError("'uri' has to be a string or unicode")

        # convert to valid url
        uri = urllib.quote(uri)

        internal_data = {'data': kwargs}
        response = self._post('query/%s' % uri, data=internal_data, timeout=self.query_timeout)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            raise NonExistError("Predictive Object '%s' cannot be found" % uri)
        else:
            raise RuntimeError('Query error status: %s, error: %s' % (response.status_code, response.text))

    def feedback(self, key, data):
        '''Provide feedback to the query result. This is a free format feedback.

        Parameters
        ----------
        key : str

        data : dict

        Examples
        --------

            >>> client = PredictiveServiceClient(config_file='some file')
            >>> client.feedback('90f1101c-d025-44b0-a7b5-b0c208c3e095',
                                {'user_clicked': 3})

        Returns
        -------
        out : dict
            Returns the server response.

        '''
        if not isinstance(key, basestring):
            raise RuntimeError("Expect key to be a string or unicode")
        if type(data) != dict:
            raise RuntimeError("Feedback 'data' needs to be dictionary type")

        data = {'data': data, 'id': key}
        return self._post('feedback', data=data)
    
    def _ping(self):
        if not hasattr(self, 'session'):
            self.session = requests.session()

        self.logger.info("Connecting to Predictive Service at %s" % self.endpoint)
        response = self.session.get(self.endpoint, verify=self.should_verify_certificate)
        if response.status_code == 200:
            self.logger.info("Successfully connected to %s" % (self.endpoint))
            return response.text
        else:
            raise RuntimeError("Error responding from service: response: %s" % str(response.text))

    def _post(self, path, data = None, timeout = None):
        if data is None:
            data = {}

        # keep api_key in the data payload for backward compatibility. 
        if self._schema_version < 7:
            data.update({'api_key': self.api_key})
        headers = {'content-type': 'application/json'}
        
        url = self.endpoint + '/' + path
        data = json.dumps(data)

        if not timeout or not isinstance(timeout, int):
            timeout = 10

        return self.session.post(url = url, data=data, headers=headers,\
               verify=self.should_verify_certificate, timeout=timeout,auth=HTTPBasicAuth('api_key', self.api_key))

    def _read_config(self, config_file):
        config_file = os.path.abspath(os.path.expanduser(config_file))
        if not os.path.isfile(config_file):
            raise RuntimeError("Path '%s' is not a file." % config_file)

        config = ConfigParser()
        config.optionxform = str
        config.read(config_file)

        if SERVICE_INFO_SECTION_NAME not in config.sections():
            raise RuntimeError("Cannot find %s section in config file %s" % (SERVICE_INFO_SECTION_NAME, config_file))

        self.endpoint = config.get(SERVICE_INFO_SECTION_NAME, 'endpoint')
        self.api_key = config.get(SERVICE_INFO_SECTION_NAME, 'api key')
        if config.has_option(SERVICE_INFO_SECTION_NAME, 'verify certificate'):
            self.should_verify_certificate = config.getboolean(SERVICE_INFO_SECTION_NAME, 'verify certificate')
        else:
            self.should_verify_certificate = False
        self.logger.info("Read configuration, endpoint: %s" % self.endpoint)

