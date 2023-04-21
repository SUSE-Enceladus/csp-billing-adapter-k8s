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

import base64
import json
import os

import csp_billing_adapter

from kubernetes.client.rest import ApiException
from kubernetes import client
from kubernetes import config as k8s_config

from csp_billing_adapter.config import Config

namespace = os.environ['ADAPTER_NAMESPACE']
usage_crd_plural = os.environ['USAGE_CRD_PLURAL']
usage_resource = os.environ['USAGE_RESOURCE']
usage_api_version = os.environ['USAGE_API_VERSION']
usage_api_group = os.environ['USAGE_API_GROUP']


@csp_billing_adapter.hookimpl
def setup_adapter(config: Config):
    k8s_config.load_kube_config()


@csp_billing_adapter.hookimpl
def save_cache(config: Config, cache: dict):
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
            return None  # Already exists
        else:
            raise


@csp_billing_adapter.hookimpl
def get_cache(config: Config):
    api_instance = client.CoreV1Api()
    try:
        resource = api_instance.read_namespaced_secret(
            'csp-adapter-cache',
            namespace,
        )
    except ApiException as error:
        if error.status == 404:
            return None
        else:
            raise
    else:
        return json.loads(base64.b64decode(resource.data.get('data')).decode())


@csp_billing_adapter.hookimpl
def update_cache(config: Config, cache: dict, replace: bool):
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
    api_instance = client.CoreV1Api()
    try:
        resp = api_instance.read_namespaced_config_map(
            'csp-config',
            namespace
        )
    except ApiException as error:
        if error.status == 404:
            return None
        else:
            raise
    else:
        return json.loads(resp.data.get('data', '{}'))


@csp_billing_adapter.hookimpl
def update_csp_config(
    config: Config,
    csp_config: Config,
    replace: bool
):
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
            return None  # Already exists
        else:
            raise


@csp_billing_adapter.hookimpl
def get_usage_data(config: Config):
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
            raise Exception(
                'Usage resource not found. Unable to log current usage.'
            )
        else:
            raise

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
