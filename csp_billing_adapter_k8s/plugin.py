#
# Copyright 2023 SUSE LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
Implements hook functions for storage and usage API in k8s environment.
The location of resources and namespace is determined by environment
variables.
"""


import base64
import inspect
import json
import logging
import os

import csp_billing_adapter

from kubernetes.client.rest import ApiException
from kubernetes import client
from kubernetes.config import (
    ConfigException,
    load_incluster_config,
    load_kube_config
)

from csp_billing_adapter.config import Config
from csp_billing_adapter.exceptions import CSPBillingAdapterException

log = logging.getLogger('CSPBillingAdapter')

namespace = os.environ['ADAPTER_NAMESPACE']
usage_crd_plural = os.environ['USAGE_CRD_PLURAL']
usage_resource = os.environ['USAGE_RESOURCE']
usage_api_version = os.environ['USAGE_API_VERSION']
usage_api_group = os.environ['USAGE_API_GROUP']


def _re_raise_api_exception(error: ApiException):
    try:
        message = json.loads(error.body)['message']
    except Exception:
        # Unexpected format use error message as is
        message = str(error)

    action = inspect.stack()[1].function.replace('_', ' ')

    raise CSPBillingAdapterException(
        f'Failed to {action}. {message}'
    ) from error


@csp_billing_adapter.hookimpl
def setup_adapter(config: Config):
    """
    Authenticate to k8s cluster

    Authentication first tries incluster config for running in a container.
    Then it will check kube config if running on control plane.
    """
    try:
        load_incluster_config()
        log.info('Loaded in cluster config.')
    except ConfigException:
        load_kube_config()
        log.info('Loaded Kube config.')


@csp_billing_adapter.hookimpl
def save_cache(config: Config, cache: dict):
    """
    Store the cache as a namespaced opaque secret in k8s cluster

    If the cache already exists nothing happens and return None.
    """
    api_instance = client.CoreV1Api()

    secret = client.V1Secret(
        metadata=client.V1ObjectMeta(
            name='csp-adapter-cache',
            namespace=namespace
        ),
        string_data={'data': json.dumps(cache)},
        type='Opaque'
    )

    try:
        api_instance.create_namespaced_secret(
            namespace,
            secret
        )
    except ApiException as error:
        if error.status == 409:
            log.info('Cache already exists.')
            return None  # Already exists
        else:
            log.error(f'Failed to save cache: {str(error)}')
            _re_raise_api_exception(error)


@csp_billing_adapter.hookimpl
def get_cache(config: Config):
    """
    Return the namespaced cache from k8s cluster

    If it does not exist return None.
    """
    api_instance = client.CoreV1Api()
    try:
        resource = api_instance.read_namespaced_secret(
            'csp-adapter-cache',
            namespace,
        )
    except ApiException as error:
        if error.status == 404:
            log.info('No existing cache found.')
            return None
        else:
            log.error(f'Failed to load cache: {str(error)}')
            _re_raise_api_exception(error)
    else:
        return json.loads(base64.b64decode(resource.data.get('data')).decode())


@csp_billing_adapter.hookimpl
def update_cache(config: Config, cache: dict, replace: bool):
    """
    Update the namespace cache secret in k8s cluster

    If replace is True the cache will be replaced with the provided
    values. Otherwise the cache is updated based on the values provided.
    """
    api_instance = client.CoreV1Api()

    if not replace:
        cache = {**get_cache(config=config), **cache}

    api_instance.patch_namespaced_secret(
        'csp-adapter-cache',
        namespace,
        {
            'data': {
                'data': base64.b64encode(json.dumps(cache).encode()).decode()
            }
        }
    )


@csp_billing_adapter.hookimpl
def get_csp_config(config: Config):
    """
    Get the namespaced csp-config config map from k8s cluster

    If the config map does not exist return None.
    """

    api_instance = client.CoreV1Api()
    try:
        resp = api_instance.read_namespaced_config_map(
            'csp-config',
            namespace
        )
    except ApiException as error:
        if error.status == 404:
            log.info('No existing CSP Config.')
            return None
        else:
            log.error('Failed to load CSP Config: {str(error)}')
            _re_raise_api_exception(error)
    else:
        return json.loads(resp.data.get('data', '{}'))


@csp_billing_adapter.hookimpl
def update_csp_config(
    config: Config,
    csp_config: Config,
    replace: bool
):
    """
    Update the namespaced csp-config config map in k8s cluster

    If replace is True replace the config map with values provided.
    Otherwise the existing map is updated using the values provided.
    """
    api_instance = client.CoreV1Api()

    if not replace:
        csp_config = {**get_csp_config(config=config), **csp_config}

    api_instance.patch_namespaced_config_map(
        'csp-config',
        namespace,
        {'data': {'data': json.dumps(csp_config)}}
    )


@csp_billing_adapter.hookimpl
def save_csp_config(
    config: Config,
    csp_config: Config
):
    """
    Save the namespaced csp-config config map to k8s cluster

    If the config map already exists do nothing and return None.
    """

    api_instance = client.CoreV1Api()
    data = {'data': json.dumps(csp_config)}

    config_map = client.V1ConfigMap(
        data=data,
        metadata=client.V1ObjectMeta(
            name='csp-config',
            namespace=namespace
        )
    )

    try:
        api_instance.create_namespaced_config_map(
            namespace,
            config_map
        )
    except ApiException as error:
        if error.status == 409:
            log.info('CSP Config already exists.')
            return None  # Already exists
        else:
            log.error(f'Failed to save CSP Config: {str(error)}')
            _re_raise_api_exception(error)


@csp_billing_adapter.hookimpl
def get_usage_data(config: Config):
    """
    Get the usage data from the CRD based on environment variables

    If the CRD is not found raise an Exception to calling scope.
    """

    api = client.CustomObjectsApi()

    try:
        resource = api.get_cluster_custom_object(
            group=usage_api_group,
            version=usage_api_version,
            plural=usage_crd_plural,
            name=usage_resource,
        )
    except ApiException as error:
        if error.status == 404:
            log.error('Usage resource not found.')
            raise Exception(
                'Usage resource not found. Unable to log current usage.'
            )
        else:
            log.error(f'Failed to load usage data: {str(error)}')
            _re_raise_api_exception(error)

    # Sanitize k8s metadata from response.
    # This leaves only the usage data provided by the product.
    try:
        del resource['metadata']
    except KeyError:
        pass

    try:
        del resource['apiVersion']
    except KeyError:
        pass

    try:
        del resource['kind']
    except KeyError:
        pass

    return resource
