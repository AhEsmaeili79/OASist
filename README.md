# OASist Client Generator

Generate type-safe Python clients from OpenAPI schemas with a beautiful CLI interface. Supports both JSON and YAML schemas with Orval-inspired configuration.

Built on top of **[openapi-python-client](https://github.com/openapi-generators/openapi-python-client)** with enhanced features and developer experience.

## Features

- 🚀 Clean, modular Python package with rich CLI interface
- 📦 Generate type-safe Python clients from OpenAPI specs (JSON/YAML)
- ✨ **Automatic code formatting with Black** (optional, enabled by default)
- 🔄 Schema sanitization and validation with security fixes
- 🎯 Orval-inspired configuration format with environment variable support
- 🏗️ Built with design patterns (Strategy, Command, Dataclass)
- ⚡ Automatic base URL detection and post-hook management
- 🎨 Beautiful terminal UI with progress indicators
- 🔒 Path traversal protection and input validation
- 🔁 Automatic retry logic for common failures

## Installation

```bash
# Install from PyPI
pip install oasist

# Install with Black formatting support (recommended)
pip install oasist[formatting]

# Or install Black separately
pip install black
```

## Quick Start

```bash
# List all configured services
oasist list

# Generate a specific client
oasist generate user

# Generate all clients
oasist generate-all

# Show service details
oasist info user

# Force regenerate existing client
oasist generate user --force

# Use custom config file
oasist -c production.json generate user

# Enable verbose/debug logging
oasist -v generate user
```

## Configuration

The generator supports both JSON and YAML OpenAPI documents. It pre-fetches the schema with optional headers/params, then generates via a local temp file to ensure consistent handling of JSON and YAML. Configuration is provided via a single JSON file using an Orval-inspired "projects" structure.

### Environment Variable Substitution

OASist supports environment variable substitution in configuration files using the `${VAR}` or `${VAR:default}` syntax:

- `${VAR}` - Replace with environment variable value (warns if not found)
- `${VAR:default}` - Replace with environment variable value or use default if not found

Example:
```json
{
  "projects": {
    "api": {
      "input": {
        "target": "${API_SCHEMA_URL:http://localhost:8000/openapi.json}"
      },
      "output": {
        "base_url": "${API_BASE_URL}",
        "dir": "api_client"
      }
    }
  }
}
```

Create a `.env` file in your project root:
```
API_SCHEMA_URL=https://api.production.com/openapi.json
API_BASE_URL=https://api.production.com
API_TOKEN=your_secret_token_here
```

### Custom Headers

You can specify custom headers for schema fetch requests, which is useful for authenticated endpoints:

```json
{
  "projects": {
    "protected_api": {
      "input": {
        "target": "https://api.example.com/openapi.json",
        "headers": {
          "Authorization": "Bearer ${API_TOKEN}",
          "X-Custom-Header": "custom-value"
        }
      },
      "output": {
        "dir": "protected_api_client"
      }
    }
  }
}
```

### Automatic Code Formatting with Black

OASist automatically formats generated Python code using **Black** (if installed). This ensures clean, consistent code style across all generated clients.

**Features:**
- ✅ Enabled by default for all projects
- ✅ Gracefully skips if Black is not installed (with helpful message)
- ✅ Can be disabled per-project via configuration
- ✅ Runs after successful client generation
- ✅ Uses Black's default configuration (88-character line length)

**Configuration:**

```json
{
  "projects": {
    "formatted_api": {
      "input": {
        "target": "https://api.example.com/openapi.json"
      },
      "output": {
        "dir": "formatted_client",
        "format_with_black": true  // Default: true
      }
    },
    "unformatted_api": {
      "input": {
        "target": "https://api.example.com/openapi.json"
      },
      "output": {
        "dir": "unformatted_client",
        "format_with_black": false  // Disable formatting
      }
    }
  }
}
```

**Installing Black:**

```bash
# Install OASist with formatting support
pip install oasist[formatting]

# Or install Black separately
pip install black
```

**What happens if Black is not installed?**
- OASist will log a warning message
- Generation will continue successfully
- Code will be generated but not formatted
- You'll see: "Black is not installed. Skipping code formatting."

### Basic Configuration

Create `oasist_config.json` in your project root:

```json
{
  "output_dir": "./test",
  "projects": {
    "user_service": {
      "input": {
        "target": "http://localhost:8001/openapi.json",
        "prefer_json": true
      },
      "output": {
        "dir": "user_service",
        "name": "User Service",
        "base_url": "http://localhost:8001",
        "package_name": "user_service",
        "format_with_black": true
      }
    },
    "test": {
      "input": {
        "target": "${TEST_SCHEMA_URL}",
        "prefer_json": true,
        "_comment": "Optional headers for the schema fetch request",
        "headers": {
          "Authorization": "Bearer ${API_TOKEN}",
          "X-API-Key": "${API_KEY:default_key}"
        }
      },
      "output": {
        "dir": "test",
        "name": "Test",
        "base_url": "${TEST_BASE_URL}",
        "package_name": "test",
        "format_with_black": true,
        "_comment": "Set format_with_black to false to disable automatic code formatting"
      }
    },
    "local_yaml": {
      "input": {
        "target": "http://localhost:8004/api/schema/"
      },
      "output": {
        "dir": "local_yaml_client",
        "name": "Local YAML API",
        "base_url": "http://localhost:8004",
        "package_name": "local_yaml_client",
        "format_with_black": false
      }
    }
  }
}
```

 

### Configuration Parameters

#### Global Parameters
| Parameter | Required | Description |
|-----------|----------|-------------|
| `output_dir` | No | Base directory for all generated clients (default: "./clients") |
| `projects` | Yes | Object containing project configurations keyed by project name |

#### Project Input Parameters
| Parameter | Required | Description |
|-----------|----------|-------------|
| `target` | Yes | URL to OpenAPI schema endpoint |
| `prefer_json` | No | If true, prefers JSON format over YAML |
| `params` | No | Query parameters for schema fetch requests |
| `headers` | No | Custom HTTP headers for schema fetch requests |

#### Project Output Parameters
| Parameter | Required | Description |
|-----------|----------|-------------|
| `dir` | Yes | Directory name for generated client |
| `name` | Yes | Human-readable service name |
| `base_url` | No | Service base URL (auto-detected if not provided) |
| `package_name` | No | Python package name (auto-generated if not provided) |
| `format_with_black` | No | Enable Black code formatting (default: true) |

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

### Global Options

```bash
# Use custom configuration file
oasist -c custom_config.json <command>
oasist --config custom_config.json <command>

# Enable verbose/debug logging
oasist -v <command>
oasist --verbose <command>

# Combine options
oasist -v -c prod.json generate-all
```

### Basic Commands

```bash
# Show general help
oasist --help
oasist help

# Show command-specific help
oasist help generate
oasist generate --help

# Show version information
oasist --version

# List all services and their generation status
oasist list

# Show detailed information about a service
oasist info <service_name>
```

### Generation Commands

```bash
# Generate client for a specific service
oasist generate <service_name>

# Force regenerate (overwrite existing)
oasist generate <service_name> --force

# Generate clients for all configured services
oasist generate-all

# Generate all with force overwrite
oasist generate-all --force
```

## Project Structure

```
OASist/
├── oasist/                 # Main package
│   ├── __init__.py         # Package exports and version
│   ├── oasist.py          # Single-file generator implementation
│   └── __pycache__/       # Python cache files
├── dist/                   # Distribution files (wheels, tarballs)
├── venv/                   # Virtual environment
├── oasist_config.json      # Configuration file
├── example.oasist_config.json  # Example configuration
├── pyproject.toml          # Project configuration
├── requirements.txt        # Dependencies
├── README.md              # This file
└── test/                  # Generated clients directory (configurable)
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

### Core Dependencies
- Python 3.8+
- openapi-python-client >= 0.26.1
- requests >= 2.31.0
- pyyaml >= 6.0.1
- rich >= 13.7.0
- python-dotenv >= 1.0.1

### Optional Dependencies
- black >= 23.0.0 (for automatic code formatting)

Install with formatting support:
```bash
pip install oasist[formatting]
```

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

### Black formatting not working
Check if Black is installed:
```bash
black --version
```

Install Black if needed:
```bash
pip install black
# Or
pip install oasist[formatting]
```

Disable formatting if not needed:
```json
{
  "output": {
    "format_with_black": false
  }
}
```

## Design Patterns Used

OASist uses several design patterns to ensure maintainability and extensibility:

- **Strategy Pattern**: `SchemaParser` protocol for pluggable JSON/YAML parsing
- **Command Pattern**: CLI commands encapsulate different operations (list, generate, info)
- **Dataclass Pattern**: Type-safe `ServiceConfig` with validation
- **Context Manager**: Temporary file management with automatic cleanup
- **Template Method**: Generator execution with customizable hooks

### Why the Patterns?

While this adds some code complexity, the benefits are:

✅ **Easy to extend** - Add new parsers, commands, or validators without touching existing code  
✅ **Type-safe** - Dataclasses provide validation and IDE autocomplete  
✅ **Testable** - Each component can be tested independently  
✅ **Maintainable** - Clear separation of concerns makes debugging easier  

For **simple use cases**, you only interact with the CLI - the patterns are invisible. For **advanced use cases**, the modular design allows programmatic usage and customization.

## Django Integration (Optional)

To use with Django management commands:

```python
# In your Django management command
from oasist import ClientGenerator, ServiceConfig

generator = ClientGenerator(output_base=Path("./clients"))
generator.add_service("user", ServiceConfig(...))
generator.generate("user")
```

## Advanced Usage

### Programmatic Usage

```python
from oasist import ClientGenerator, ServiceConfig
from pathlib import Path

# Create generator with custom output directory
generator = ClientGenerator(output_base=Path("./my_clients"))

# Add services
generator.add_service("api", ServiceConfig(
    name="API Service",
    schema_url="https://api.example.com/openapi.json",
    output_dir="api_client",
    format_with_black=True  # Enable Black formatting
))

# Generate
generator.generate("api", force=True)

# Or generate all
generator.generate_all(force=True)

# Note: You can also modify the OUTPUT_DIR constant at the top of the file
# for persistent changes instead of passing output_base parameter
```

### Custom Base URL and Formatting Options

```python
generator.add_service("prod", ServiceConfig(
    name="Production API",
    schema_url="https://api.example.com/openapi.json",
    output_dir="prod_client",
    base_url="https://api.example.com",  # Custom base URL
    format_with_black=True  # Enable automatic Black formatting
))

# Disable formatting for specific service
generator.add_service("legacy", ServiceConfig(
    name="Legacy API",
    schema_url="https://legacy.example.com/openapi.json",
    output_dir="legacy_client",
    format_with_black=False  # Disable formatting for this service
))
```

## Examples

### Example 1: Generate User Service Client

```bash
$ oasist generate user_service
INFO: ✓ Generated client: user_service → test/user_service
```

### Example 2: List All Services

```bash
$ oasist list

📋 Configured Services:
  ○ user_service        User Service                  http://localhost:8001/openapi.json
  ○ communication_service Communication Service       http://localhost:8002/openapi.json
  ○ local_yaml          Local YAML API                http://localhost:8004/api/schema/
```

### Example 3: Service Information

```bash
$ oasist info user_service

📦 Service: user_service
   Name:        User Service
   Schema URL:  http://localhost:8001/openapi.json
   Output:      test/user_service
   Status:      Not generated
```

## Contributing

Contributions are welcome! To extend or modify:

1. Fork the repository
2. Create a feature branch
3. Make your changes with appropriate tests
4. Submit a pull request

### Development Setup

```bash
# Clone the repository
git clone https://github.com/AhEsmaeili79/oasist.git
cd oasist

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install in development mode
pip install -e .

# Run tests
pytest
```

## License

MIT License - See [LICENSE](LICENSE) file for details

Copyright (c) 2024 AH Esmaeili

## Support

For issues or questions:
- Check the Troubleshooting section
- Review the OpenAPI schema URL accessibility
- Verify all dependencies are installed
- Enable debug logging for detailed error information
