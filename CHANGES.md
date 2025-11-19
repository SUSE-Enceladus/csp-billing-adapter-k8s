v1.1.0 (2025-11-19)
-------------------

- Make environtment variables optional. If the get usage data function is
  overwritten by a product specific plugin the values will be retrieved
  in the plugin. If there is no product plugin the environment variables
  are all required. The namespace environment variable is always required.

v1.0.0 (2024-06-03)
-------------------

- Switch spec build to python 3.11

v0.4.0 (2024-01-12)
-------------------

- Add metering archive hook implementations.

v0.3.0 (2023-07-20)
-------------------

- Implement get version hookspec

v0.2.0 (2023-06-30)
-------------------

- Parse APIExceptions from k8s to remove embedded json

v0.1.0 (2023-05-19)
-------------------

- Add logging and cover all error cases in tests

v0.0.1 (2023-05-03)
-------------------

- initial release
