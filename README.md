# OASist Client Generator

Automated Python client generation from OpenAPI schemas. Simple, clean, and efficient.

## Features

- 🚀 Single-file implementation (no complexity)
- 📦 Generate type-safe Python clients from OpenAPI specs
- 🔄 Easy client updates and management
- 🎯 CLI interface for all operations
- 🏗️ Built with design patterns (Factory, Command)

## Installation

```bash
# Install dependencies
pip install openapi-python-client requests pyyaml

# Make executable (optional)
chmod +x oasist_client.py
```

## Quick Start

```bash
# List all configured services
python oasist_client.py list

# Generate a specific client
python oasist_client.py generate user

# Generate all clients
python oasist_client.py generate-all

# Show service details
python oasist_client.py info user

# Force regenerate existing client
python oasist_client.py generate user --force
```

## Configuration

### Configuration

The generator supports both JSON and YAML OpenAPI documents. It pre-fetches the schema with optional headers/params, then generates via a local temp file to ensure consistent handling of JSON and YAML. Configuration is provided via a single JSON file.

Create `oasist_config.json` in your project root:

```json
{
  "output_dir": "./clients",
  "services": [
    {
      "key": "public_json",
      "name": "Public JSON API",
      "schema_url": "http://91.99.51.233:8001/openapi.json",
      "output_dir": "public_json_client",
      "base_url": "",
      "package_name": "",
      "prefer_json": true
    },
    {
      "key": "local_yaml",
      "name": "Local YAML API",
      "schema_url": "http://localhost:8004/api/schema/",
      "output_dir": "local_yaml_client",
      "base_url": "http://localhost:8004",
      "package_name": "",
      "prefer_json": true,
      "request_headers": {
        "Accept": "application/vnd.oai.openapi+json, application/json"
      }
    }
  ]
}
```

 

### Configuration Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `output_dir` | No | Base directory for all generated clients |
| `services` | Yes | Array of service configurations |
| `key` | Yes | Unique identifier for the service |
| `name` | Yes | Human-readable service name |
| `schema_url` | Yes | URL to OpenAPI schema endpoint |
| `output_dir` | Yes | Directory name for generated client |
| `base_url` | No | Service base URL (auto-detected if not provided) |
| `package_name` | No | Python package name (auto-generated if not provided) |
| `request_headers` | No | Extra HTTP headers for schema fetch (e.g., `Accept`) |
| `request_params` | No | Extra query parameters for schema fetch |
| `prefer_json` | No | If true, sets `Accept` to prefer OpenAPI JSON |

### ServiceConfig Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | Yes | Human-readable service name |
| `schema_url` | Yes | URL to OpenAPI schema endpoint |
| `output_dir` | Yes | Directory name for generated client |
| `base_url` | No | Service base URL (auto-detected if not provided) |
| `package_name` | No | Python package name (auto-generated if not provided) |

## Usage in Code

```python
# Import the generated client
from clients.user_service.user_service_client import Client

# Initialize client
client = Client(base_url="http://192.168.100.11:8011")

# Use the client
response = client.users.list_users()
user = client.users.get_user(user_id=123)
```

## All Commands

### Basic Commands

```bash
# Show general help
python oasist_client.py --help
python oasist_client.py help

# Show command-specific help
python oasist_client.py help generate
python oasist_client.py generate --help

# List all services and their generation status
python oasist_client.py list

# Show detailed information about a service
python oasist_client.py info <service_name>
```

### Generation Commands

```bash
# Generate client for a specific service
python oasist_client.py generate <service_name>

# Force regenerate (overwrite existing)
python oasist_client.py generate <service_name> --force

# Generate clients for all configured services
python oasist_client.py generate-all

# Generate all with force overwrite
python oasist_client.py generate-all --force
```

### Update Commands

```bash
# Update existing client (alias for generate --force)
python oasist_client.py generate <service_name> --force
```

## Project Structure

```
oasist/
├── oasist_client.py       # Single-file generator (all-in-one)
├── README.md               # This file
├── .gitignore             # Git ignore rules
└── clients/               # Generated clients directory
    ├── user_service/      # Generated client example
    │   ├── pyproject.toml
    │   └── user_service_client/
    │       ├── __init__.py
    │       ├── client.py
    │       ├── api/
    │       ├── models/
    │       └── types.py
    └── [other_services]/  # Additional generated clients
```

## Requirements

- Python 3.8+
- openapi-python-client
- requests
- pyyaml

## Troubleshooting

### Schema URL not accessible
Ensure the service is running and the schema endpoint is correct:
```bash
curl http://192.168.100.11:8011/api/schema/
```

### Permission errors
Ensure write permissions for the clients directory:
```bash
chmod -R u+w clients/
```

### Client generation fails
Check if openapi-python-client is installed:
```bash
pip install --upgrade openapi-python-client
```

Enable debug logging in code:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Design Patterns Used

- **Factory Pattern**: `ClientGenerator` creates configured clients
- **Command Pattern**: CLI commands encapsulate operations
- **Dataclass Pattern**: Immutable configuration objects
- **Singleton Pattern**: Single generator instance manages all services

## Django Integration (Optional)

To use with Django management commands:

```python
# In your Django management command
from oasist_client import ClientGenerator, ServiceConfig

generator = ClientGenerator(output_base=Path("./clients"))
generator.add_service("user", ServiceConfig(...))
generator.generate("user")
```

## Advanced Usage

### Programmatic Usage

```python
from oasist_client import ClientGenerator, ServiceConfig
from pathlib import Path

# Create generator with custom output directory
generator = ClientGenerator(output_base=Path("./my_clients"))

# Add services
generator.add_service("api", ServiceConfig(
    name="API Service",
    schema_url="https://api.example.com/openapi.json",
    output_dir="api_client"
))

# Generate
generator.generate("api", force=True)

# Or generate all
generator.generate_all(force=True)

# Note: You can also modify the OUTPUT_DIR constant at the top of the file
# for persistent changes instead of passing output_base parameter
```

### Custom Base URL

```python
generator.add_service("prod", ServiceConfig(
    name="Production API",
    schema_url="https://api.example.com/schema/",
    output_dir="prod_client",
    base_url="https://api.example.com"  # Custom base URL
))
```

## Examples

### Example 1: Generate User Service Client

```bash
$ python oasist_client.py generate user
INFO: ✓ Generated client: user → clients/user_service
```

### Example 2: List All Services

```bash
$ python oasist_client.py list

📋 Configured Services:
  ✓ user                User Service                  http://192.168.100.11:8011/api/schema/
  ○ payment             Payment Service               http://192.168.100.11:8012/api/schema/
```

### Example 3: Service Information

```bash
$ python oasist_client.py info user

📦 Service: user
   Name:        User Service
   Schema URL:  http://192.168.100.11:8011/api/schema/
   Output:      clients/user_service
   Status:      Generated ✓
   Modified:    2025-10-05 14:30:22
```

## Contributing

This is a single-file tool designed for simplicity. To extend:

1. Add services in the `main()` function
2. Modify `ClientGenerator` class for custom behavior
3. Add new commands in the command handling section

## License

MIT License - Part of the project

## Support

For issues or questions:
- Check the Troubleshooting section
- Review the OpenAPI schema URL accessibility
- Verify all dependencies are installed
- Enable debug logging for detailed error information
