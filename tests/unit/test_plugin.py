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
import pytest

from datetime import datetime

from unittest.mock import Mock, patch

from kubernetes.config import ConfigException
from kubernetes.client.rest import ApiException

from csp_billing_adapter_k8s import plugin
from csp_billing_adapter.config import Config
from csp_billing_adapter.adapter import get_plugin_manager
from csp_billing_adapter.exceptions import CSPBillingAdapterException

pm = get_plugin_manager()
config = Config.load_from_file(
    'tests/data/good_config.yaml',
    pm.hook
)
now = datetime.now().isoformat()
cache = {
    'adapter_start_time': now,
    'next_bill_time': now,
    'next_reporting_time': now,
    'usage_records': [],
    'last_bill': {}
}
csp_config = {
    'billing_api_access_ok': True,
    'timestamp': now,
    'expire': now,
    'errors': []
}
metering_archive = [
  {
        'billing_time': '2024-02-09T18:11:59.527064+00:00',
        'billing_status': {
            'tier_1': {
                'record_id': '123',
                'status': 'succeeded'
            }
        },
        'billed_usage': {
            'tier_1': 10
        },
        'usage_records': [
            {
                'managed_node_count': 10,
                'reporting_time': '2024-02-09T18:11:59.527064+00:00',
                'base_product': 'cpe:/o:suse:product:v1.2.3'
            }
        ]
    }
]


def create_exception(status: int):
    response = Mock()
    response.status = status
    response.reason = 'Borked'
    response.data = '"message": "Borked!"'
    response.getheaders.return_value = None
    return ApiException(http_resp=response)


@patch('csp_billing_adapter_k8s.plugin.load_kube_config')
@patch('csp_billing_adapter_k8s.plugin.load_incluster_config')
def test_setup(mock_load_incluster_cfg, mock_load_kube_cfg):
    # Test fallback
    mock_load_incluster_cfg.side_effect = ConfigException
    plugin.setup_adapter(config)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_save_cache_exists(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.create_namespaced_secret.side_effect = create_exception(status=409)
    response = plugin.save_cache(config, cache)
    assert response is None


@patch('csp_billing_adapter_k8s.plugin.client')
def test_save_cache_error(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.create_namespaced_secret.side_effect = create_exception(status=404)

    with pytest.raises(CSPBillingAdapterException):
        plugin.save_cache(config, cache)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_save_cache(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.create_namespaced_secret.return_value = None
    plugin.save_cache(config, cache)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_cache(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api

    response = Mock()
    response.data = {
        'data': base64.b64encode(json.dumps(cache).encode()).decode()
    }
    api.read_namespaced_secret.return_value = response
    res = plugin.get_cache(config)
    assert res['adapter_start_time'] == now


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_cache_not_exists(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api

    api.read_namespaced_secret.side_effect = create_exception(status=404)
    res = plugin.get_cache(config)
    assert res is None


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_cache_error(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.read_namespaced_secret.side_effect = create_exception(status=400)

    with pytest.raises(CSPBillingAdapterException):
        plugin.get_cache(config)


@patch('csp_billing_adapter_k8s.plugin.get_cache')
@patch('csp_billing_adapter_k8s.plugin.client')
def test_update_cache(mock_client, mock_get_cache):
    mock_get_cache.return_value = cache

    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.read_namespaced_secret.return_value = None

    data = {'other': 'info'}
    plugin.update_cache(config, data, replace=False)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_save_csp_config_exists(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.create_namespaced_config_map.side_effect = create_exception(status=409)
    response = plugin.save_csp_config(config, csp_config)
    assert response is None


@patch('csp_billing_adapter_k8s.plugin.client')
def test_save_csp_config_error(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.create_namespaced_config_map.side_effect = create_exception(status=400)

    with pytest.raises(CSPBillingAdapterException):
        plugin.save_csp_config(config, csp_config)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_save_csp_config(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.create_namespaced_config_map.return_value = None
    plugin.save_csp_config(config, csp_config)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_csp_config(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api

    response = Mock()
    response.data = {
        'data': json.dumps(csp_config)
    }
    api.read_namespaced_config_map.return_value = response
    res = plugin.get_csp_config(csp_config)
    assert res['billing_api_access_ok']


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_csp_config_not_exists(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api

    api.read_namespaced_config_map.side_effect = create_exception(status=404)
    res = plugin.get_csp_config(config)
    assert res is None


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_csp_config_error(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.read_namespaced_config_map.side_effect = create_exception(status=400)

    with pytest.raises(CSPBillingAdapterException):
        plugin.get_csp_config(config)


@patch('csp_billing_adapter_k8s.plugin.get_csp_config')
@patch('csp_billing_adapter_k8s.plugin.client')
def test_update_csp_config(mock_client, mock_get_csp_config):
    mock_get_csp_config.return_value = cache

    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.read_namespaced_config_map.return_value = None

    data = {'other': 'info'}
    plugin.update_csp_config(config, data, replace=False)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_usage(mock_client):
    resource = {
        'timestamp': now,
        'managed_node_count': 10
    }
    api = Mock()
    api.get_cluster_custom_object.return_value = resource
    mock_client.CustomObjectsApi.return_value = api

    response = plugin.get_usage_data(config)
    assert response['timestamp'] == now


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_usage_not_exists(mock_client):
    api = Mock()
    api.get_cluster_custom_object.side_effect = create_exception(status=404)
    mock_client.CustomObjectsApi.return_value = api

    with pytest.raises(Exception):
        plugin.get_usage_data(config)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_usage_error(mock_client):
    api = Mock()
    api.get_cluster_custom_object.side_effect = create_exception(status=400)
    mock_client.CustomObjectsApi.return_value = api

    with pytest.raises(CSPBillingAdapterException):
        plugin.get_usage_data(config)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_usage_error_unexpected_format(mock_client):
    api = Mock()
    api.get_cluster_custom_object.side_effect = ApiException(status=400)
    mock_client.CustomObjectsApi.return_value = api

    with pytest.raises(CSPBillingAdapterException):
        plugin.get_usage_data(config)


def test_get_version():
    version = plugin.get_version()
    assert version[0] == 'k8s_plugin'
    assert version[1]


def test_get_archive_location():
    result = plugin.get_archive_location()
    assert result == 'metering-archive'


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_metering_archive(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api

    response = Mock()
    response.data = {
        'archive': json.dumps(metering_archive)
    }
    api.read_namespaced_config_map.return_value = response
    res = plugin.get_metering_archive(config)
    assert res == metering_archive


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_metering_archive_not_exists(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api

    api.read_namespaced_config_map.side_effect = create_exception(status=404)
    res = plugin.get_metering_archive(config)
    assert res == []


@patch('csp_billing_adapter_k8s.plugin.client')
def test_get_metering_archive_error(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.read_namespaced_config_map.side_effect = create_exception(status=400)

    with pytest.raises(CSPBillingAdapterException):
        plugin.get_metering_archive(config)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_save_metering_archive_error(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.create_namespaced_config_map.side_effect = create_exception(status=400)

    response = Mock()
    response.data = {}
    api.read_namespaced_config_map.return_value = response

    with pytest.raises(CSPBillingAdapterException):
        plugin.save_metering_archive(config, metering_archive)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_update_metering_archive(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.patch_namespaced_config_map.return_value = None

    response = Mock()
    response.data = {
        'archive': json.dumps(metering_archive)
    }
    api.read_namespaced_config_map.return_value = response

    plugin.save_metering_archive(config, metering_archive)


@patch('csp_billing_adapter_k8s.plugin.client')
def test_save_metering_archive(mock_client):
    api = Mock()
    mock_client.CoreV1Api.return_value = api
    api.patch_namespaced_config_map.return_value = None

    response = Mock()
    response.data = {}
    api.read_namespaced_config_map.return_value = response

    plugin.save_metering_archive(config, metering_archive)
