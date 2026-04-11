# Biopeak Nexus Backend

A robust Biopeak Management Backend built with Django, Django REST Framework, PostgeSQL, etc

## Features

- **JWT Authentication**: Secure token-based authentication with access and refresh tokens
- **Custom User Model**: Email-based authentication with extended user profile
- **PostgreSQL Database**: Production-ready database configuration
- **Standardized API Responses**: Consistent response format across all endpoints
- **Password Management**: Complete password reset and change functionality
- **Email Integration**: Password reset via email notifications

## Tech Stack

- **Backend**: Django 6.x, Django REST Framework
- **Database**: PostgreSQL
- **Authentication**: JWT (JSON Web Tokens)
- **Email**: Django Email Backend
- **Environment**: Python 3.14
- **Package Manager**: uv

## Installation

### Prerequisites

- Python 3.14 or higher
- PostgreSQL 17
- uv (package manager)

### Project Structure

The project uses `pyproject.toml` for dependency management instead of `requirements.txt`.

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd <project-name>
   ```

2. **Initialize a virtual environment using uv**
   ```bash
   uv venv
   ```

3. **Activate virtual environment**
   ```bash
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

4. **Install dependencies using uv**
   ```bash
   uv sync
   ```

5. **Environment Configuration**
   ### Environment Variables for Production
   
   For detailed production configuration, see [ENVIRONMENT.md](docs/ENVIRONMENT.md).
   
   Quick production setup:
   
   ```env
   SECRET_KEY=your-production-secret-key
   
   # Production Database
   PRD_DB_NAME=production_db_name
   PRD_DB_USER=production_db_user
   PRD_DB_PASSWORD=production_db_password
   PRD_DB_HOST=your-db-host
   PRD_DB_PORT=5432
   
   # Production Email
   PRD_EMAIL_HOST=your-smtp-host
   PRD_EMAIL_PORT=587
   PRD_EMAIL_HOST_USER=your-email
   PRD_EMAIL_HOST_PASSWORD=your-email-password
   PRD_DEFAULT_FROM_EMAIL=your-email
   
   # Production Redis (Required)
   PRD_REDIS_HOST=your-redis-host:6379
   
   # AWS S3 Storage
   AWS_S3_ACCESS_KEY_ID=your-aws-access-key
   AWS_S3_SECRET_ACCESS_KEY=your-aws-secret-key
   AWS_STORAGE_BUCKET_NAME=your-bucket-name
   AWS_S3_REGION_NAME=your-region
   ```

6. **Database Setup**
   ```bash
   uv run manage.py makemigrations
   uv run manage.py migrate
   ```

7. **Create Superuser**
   ```bash
   uv run manage.py createsuperuser
   ```

8. **Run the server**
   ```bash
   uv run manage.py runserver
   ```

## Package Management with uv

This project uses [uv](https://github.com/astral-sh/uv) as the package manager, which is faster and more reliable than
pip.

### Common uv commands:

- **Install dependencies**: `uv sync`
- **Add new package**: `uv add package-name`
- **Add development dependency**: `uv add --dev package-name`
- **Remove package**: `uv remove package-name`
- **Update dependencies**: `uv sync --upgrade`
- **Run Django commands**: `uv run manage.py <command>`
- **Export requirements**: `uv export --format requirements-txt --output-file requirements.txt`

## User Profile Model

The application uses a custom user model which extends profile model having the following fields:

```python
from django.utils.text import gettext_lazy as _
from django.db import models


class Gender:
    MALE = "0"
    FEMALE = "1"

    CHOICES = (
        (MALE, "Male"),
        (FEMALE, "Female")
    )


class AbstractUserProfile(models.Model):
    first_name = models.CharField(_("first name"), max_length=100, null=True, blank=True)
    last_name = models.CharField(_("last name"), max_length=100, null=True, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)

    gender = models.CharField(max_length=1, choices=Gender.CHOICES, null=True, blank=True)
    image = models.ImageField(upload_to='users/images/', null=True, blank=True)

    class Meta:
        abstract = True

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = "%s %s" % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name

```

### Gender Choices

- Male
- Female
- Other
- Prefer not to say

## Database Configuration

The project uses PostgreSQL as the primary database. Ensure PostgreSQL is installed and running, then update your `.env`
file with the correct database credentials.

### Database Settings

```python
from decouple import config

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', 'localhost'),
        'PORT': config('DB_PORT', '5432'),
    }
}
```

## Email Configuration

Configure email settings for password reset functionality:

```python
from decouple import config

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = int(config('EMAIL_PORT', 587))
EMAIL_USE_TLS = config('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = config('EMAIL_HOST_USER')
```

## Response Format

All API responses follow a standardized format:

### Success Response

```jsonc
{
    "success": true,
    "detail": "Operation completed successfully",
    "data": {
        // Response data here
    }
}
```

### Error Response

```json
{
  "success": false,
  "detail": "Error description",
  "errors": {
    "field_name": [
      "Error message for this field"
    ]
  }
}
```

### HTTP Status Codes

- `200`: Success
- `201`: Created
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `500`: Internal Server Error

## Authentication

The API uses JWT (JSON Web Tokens) for authentication. Include the access token in the Authorization header:

```
Authorization: Bearer <access_token>
```

### Token Lifecycle

- **Access Token**: Valid for 60 minutes (configurable)
- **Refresh Token**: Valid for 7 days (configurable)

## API Endpoints

### Authentication Endpoints

#### 1. Login

**Endpoint**: `POST /auth/login/`

**Request Payload**:

```json
{
  "email": "user@example.com",
  "password": "your_password"
}
```

**Success Response**:

```json
{
  "success": true,
  "detail": "Login successful",
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
  }
}
```

#### 2. Token Refresh

**Endpoint**: `POST /auth/refresh/`

**Request Payload**:

```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Success Response**:

```json
{
  "success": true,
  "detail": "Token refreshed successfully",
  "data": {
     "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...", 
     "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
  }
}
```

### Password Management Endpoints

#### 3. Request Password Reset

**Endpoint**: `POST /auth/forgot-password/`

**Request Payload**:

```json
{
  "email": "user@example.com"
}
```

**Success Response**:

```json
{
  "success": true,
  "detail": "Password reset email sent successfully"
}
```

#### 4. Verify Reset Token

**Endpoint**: `POST /auth/check-password-token/`

**Request Payload**:

```json
{
  "token": "reset-token-here"
}
```

**Success Response**:

```json
{
  "success": true,
  "detail": "Token is valid"
}
```

#### 5. Reset Password

**Endpoint**: `POST /auth/reset-password/`

**Request Payload**:

```json
{
  "token": "reset-token-here",
  "password1": "new_password123",
  "password2": "new_password123"
}
```

**Success Response**:

```json
{
  "success": true,
  "detail": "Password reset successfully"
}
```

#### 6. Change Password (Authenticated)

**Endpoint**: `POST /auth/change-password/`

**Headers**: `Authorization: Bearer <access_token>`

**Request Payload**:

```json
{
  "password": "current_password123",
  "password1": "new_password123",
  "password2": "new_password123"
}
```

**Success Response**:

```json
{
  "success": true,
  "detail": "Password changed successfully"
}
```

## Security Features

- **CORS Configuration**: Configured for cross-origin requests
- **JWT Security**: Secure token generation and validation
- **Password Validation**: Django's built-in password validators
- **Email Verification**: Token-based password reset
- **User Input Validation**: Comprehensive form validation

## Testing

Run the test suite:

```bash
uv run manage.py test
```

For specific app testing:

```bash
uv run manage.py test accounts
```

## Deployment

### Environment Variables for Production

```env
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com
SECRET_KEY=your-production-secret-key

# Database
PRD_DB_NAME=production_db_name
PRD_DB_USER=production_db_user
PRD_DB_PASSWORD=production_db_password
PRD_DB_HOST=your-db-host
PRD_DB_PORT=5432

# Email
PRD_EMAIL_HOST=your-smtp-host
PRD_EMAIL_PORT=587
PRD_EMAIL_HOST_USER=your-email
PRD_EMAIL_HOST_PASSWORD=your-email-password
```

### Static Files

```bash
uv run manage.py collectstatic --noinput --clear
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Commit your changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/new-feature`)
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions, please open an issue in the repository or contact the development team.

---

**Note**: Remember to keep your `.env` file secure and never commit it to version control. Always use environment
variables for sensitive configuration in production.