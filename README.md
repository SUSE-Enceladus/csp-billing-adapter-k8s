# CSP Billing Adapter Kubernetes Plugin

This is a plugin for
[csp-billing-adapter](https://github.com/SUSE-Enceladus/csp-billing-adapter)
that provides storage hook implementations. It also implements the
get_usage_data hook for the adapter. The namespace is configured based on
the **ADAPTER_NAMESPACE** environment variable which is expected to be set
in the container.

The following function hooks are implemented:

## Setup

### Setup adapter

The `setup_adapter` function authenticates the current session. It
tries both the in cluster config and Kube config. If both fail an
exception is raised.

## Cache

### save_cache

Stores the adapter cache in an opaque secret named *csp-adapter-cache* in
the namespace determined by the above environment varaible. If the cache
already exists no save is performed. In this case it's expected to use the
`update_cache` function instead.

### update_cache

Updates or replaces the adapter cache in the *csp-adapter-cache* secret
using the configured namespace.

### get_cache

Retrieves the cache from the secret named *csp-adapter-cache*. If the cache
is not found `None` is returned.

## CSP Config

### save_csp_config

Stores the adapter csp config in configMap named *csp-config* in the
configured namespace. If *csp-config* already exists nothing is saved.
It is expected to use `update_csp_config` to make updates to an existing
*csp-config*.

### update_csp_config

Updates or replace the configMap named *csp-config* in the configured
namespace.

### get_csp_config

Retrieves the csp config from the configMap named *csp-config*. If the
csp config is not found `None` is returned.

## Usage

### get_usage_data

Retrieves usage data from the configured custom resource definition (CRD).
The location, name and namespace of the CR are configured using environment
variables:

**ADAPTER_NAMESPACE**:The namespace where the adapter is deployed.

**USAGE_CRD_PLURAL**: The plural name of the K8s CRD.

**USAGE_RESOURCE**: The name of the CRD object that contains the usage data.

**USAGE_API_VERSION**: The API version of the usage CRD to use. Example "v1.

**USAGE_API_GROUP**: The API group where the CRD exists.

The CRD is expected to have a number of fields. *reporting_time* is required
and is expected to be a RFC 3339 compliant in UTC with the following format:
YYYY-MM-DDTHH:MM:SS.FFFFFF+00:00. *base_product* is optional and if it's
provided it is a string containing information about the product name and
version. At least one usage field but there can be more than one.
