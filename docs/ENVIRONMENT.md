# Environment Configuration Guide

This document provides comprehensive guidance for configuring environment variables across different deployment
environments (development, staging, production).

## Overview

The application uses environment variables for configuration across different environments. All configuration is managed
through a `.env` file in the project root with environment-specific prefixes (DEV_, STG_, PRD_).

## Core Settings

### Required Settings

```env
SECRET_KEY=your-django-secret-key-here
```

## Environment-Specific Database Configuration

Configure database settings for your target environment:

### Development Database

```env
DEV_DB_NAME=your_dev_database_name
DEV_DB_USER=your_dev_database_user
DEV_DB_PASSWORD=your_dev_database_password
DEV_DB_HOST=localhost
DEV_DB_PORT=5432
```

### Staging Database

```env
STG_DB_NAME=your_staging_database_name
STG_DB_USER=your_staging_database_user
STG_DB_PASSWORD=your_staging_database_password
STG_DB_HOST=your_staging_db_host
STG_DB_PORT=5432
```

### Production Database

```env
PRD_DB_NAME=your_production_database_name
PRD_DB_USER=your_production_database_user
PRD_DB_PASSWORD=your_production_database_password
PRD_DB_HOST=your_production_db_host
PRD_DB_PORT=5432
```

## Email Configuration

Configure email settings for password reset and notifications:

### Development Email

```env
DEV_EMAIL_HOST=smtp.gmail.com
DEV_EMAIL_PORT=587
DEV_EMAIL_HOST_USER=your-dev-email@gmail.com
DEV_EMAIL_HOST_PASSWORD=your-app-password
DEV_DEFAULT_FROM_EMAIL=your-dev-email@gmail.com
```

### Staging Email

```env
STG_EMAIL_HOST=your-staging-smtp-host
STG_EMAIL_PORT=587
STG_EMAIL_HOST_USER=your-staging-email@domain.com
STG_EMAIL_HOST_PASSWORD=your-staging-email-password
STG_DEFAULT_FROM_EMAIL=your-staging-email@domain.com
```

### Production Email

```env
PRD_EMAIL_HOST=your-production-smtp-host
PRD_EMAIL_PORT=587
PRD_EMAIL_HOST_USER=your-production-email@domain.com
PRD_EMAIL_HOST_PASSWORD=your-production-email-password
PRD_DEFAULT_FROM_EMAIL=your-production-email@domain.com
```

## Redis Configuration (Optional)

Redis is used for websockets and caching:

```env
# Development
DEV_REDIS_HOST=localhost:6379

# Staging
STG_REDIS_HOST=your-staging-redis-host:6379

# Production (Required)
PRD_REDIS_HOST=your-production-redis-host:6379
```

## AWS S3 Storage Configuration

For staging and production file storage:

```env
AWS_S3_ACCESS_KEY_ID=your-aws-access-key-id
AWS_S3_SECRET_ACCESS_KEY=your-aws-secret-access-key
AWS_STORAGE_BUCKET_NAME=your-s3-bucket-name
AWS_S3_REGION_NAME=us-east-1
AWS_S3_ENDPOINT_URL=https://s3.amazonaws.com
AWS_S3_CUSTOM_DOMAIN=your-custom-domain.com
```

## Password Reset URLs (Optional)

Frontend URLs for password reset redirects:

```env
DEV_PASSWORD_RESET_URL=http://localhost:3000/reset-password
STG_PASSWORD_RESET_URL=https://staging.yourdomain.com/reset-password
PRD_PASSWORD_RESET_URL=https://yourdomain.com/reset-password
```

## Google Calendar Integration

Credentials for `integrations/google_calendar/` (staff Google Calendar sync -
see `docs/google-calendar-integration.md`). Same per-environment prefix
pattern as everything else on this page:

```env
DEV_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
DEV_GOOGLE_CLIENT_SECRET=your-client-secret
DEV_GOOGLE_REDIRECT_URI=http://127.0.0.1:8001/google-calendar/callback/
DEV_GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY=
```

Staging/production use the same names with `STG_`/`PRD_` prefixes.

`GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY` isn't a password you make up - generate
one with:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

If it ever leaks, treat it like a leaked password: rotate it and have every
connected staff member reconnect their calendar.

## User Management

### Django Superuser (for automated deployment)

```env
DJANGO_SUPERUSER_EMAIL=superuser@yourdomain.com
DJANGO_SUPERUSER_PASSWORD=secure_superuser_password
```

## Environment Variable Categories

| Category     | Required | Description                                  |
|--------------|----------|----------------------------------------------|
| **Core**     | ✅        | Essential Django settings                    |
| **Database** | ✅        | PostgreSQL connection settings               |
| **Email**    | ✅        | SMTP configuration for notifications         |
| **Redis**    | ⚠️       | Required for production, optional for dev    |
| **AWS S3**   | ⚠️       | Required for staging/production file storage |
| **URLs**     | ❌        | Optional password reset frontend URLs        |
| **Users**    | ❌        | Optional automated user creation             |

## Environment Detection

The application automatically detects the environment based on the `DJANGO_SETTINGS_MODULE` variable. The variable can have the following values:

- `core.settings.development` (for development, default)
- `core.settings.staging` (for staging)
- `core.settings.production` (for production)


## Complete Example Configurations

### Development Environment (.env)

```env
SECRET_KEY=django-insecure-your-secret-key-here

# Development Database
DEV_DB_NAME=myproject_dev
DEV_DB_USER=postgres
DEV_DB_PASSWORD=password123
DEV_DB_HOST=localhost
DEV_DB_PORT=5432

# Development Email
DEV_EMAIL_HOST=smtp.gmail.com
DEV_EMAIL_PORT=587
DEV_EMAIL_HOST_USER=myemail@gmail.com
DEV_EMAIL_HOST_PASSWORD=myapppassword
DEV_DEFAULT_FROM_EMAIL=myemail@gmail.com

# Optional Redis
DEV_REDIS_HOST=localhost:6379

# Optional Password Reset URL
DEV_PASSWORD_RESET_URL=http://localhost:3000/reset-password
```

### Staging Environment (.env)

```env
SECRET_KEY=your-staging-secret-key-here

# Staging Database
STG_DB_NAME=myproject_staging
STG_DB_USER=myproject_user
STG_DB_PASSWORD=secure_staging_password
STG_DB_HOST=staging-db.amazonaws.com
STG_DB_PORT=5432

# Staging Email
STG_EMAIL_HOST=smtp.sendgrid.net
STG_EMAIL_PORT=587
STG_EMAIL_HOST_USER=apikey
STG_EMAIL_HOST_PASSWORD=SG.your-sendgrid-api-key
STG_DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# Staging Redis (Required)
STG_REDIS_HOST=staging-redis.amazonaws.com:6379

# AWS S3 Storage
AWS_S3_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_S3_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_STORAGE_BUCKET_NAME=myproject-staging-media
AWS_S3_REGION_NAME=us-east-1
AWS_S3_ENDPOINT_URL=https://s3.amazonaws.com
AWS_S3_CUSTOM_DOMAIN=media.yourdomain.com

# Staging URLs
STG_PASSWORD_RESET_URL=https://yourdomain.com/reset-password

# Superuser for deployment
DJANGO_SUPERUSER_EMAIL=admin@yourdomain.com
DJANGO_SUPERUSER_PASSWORD=secure_admin_password
```

### Production Environment (.env)

```env
SECRET_KEY=your-production-secret-key-here

# Production Database
PRD_DB_NAME=myproject_production
PRD_DB_USER=myproject_user
PRD_DB_PASSWORD=secure_production_password
PRD_DB_HOST=production-db.amazonaws.com
PRD_DB_PORT=5432

# Production Email
PRD_EMAIL_HOST=smtp.sendgrid.net
PRD_EMAIL_PORT=587
PRD_EMAIL_HOST_USER=apikey
PRD_EMAIL_HOST_PASSWORD=SG.your-sendgrid-api-key
PRD_DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# Production Redis (Required)
PRD_REDIS_HOST=production-redis.amazonaws.com:6379

# AWS S3 Storage
AWS_S3_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_S3_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_STORAGE_BUCKET_NAME=myproject-production-media
AWS_S3_REGION_NAME=us-east-1
AWS_S3_ENDPOINT_URL=https://s3.amazonaws.com
AWS_S3_CUSTOM_DOMAIN=media.yourdomain.com

# Production URLs
PRD_PASSWORD_RESET_URL=https://yourdomain.com/reset-password

# Superuser for deployment
DJANGO_SUPERUSER_EMAIL=admin@yourdomain.com
DJANGO_SUPERUSER_PASSWORD=secure_admin_password
```

## Security Best Practices

### General Security

- Never commit your `.env` file to version control
- Add `.env` to your `.gitignore` file
- Use strong, unique passwords for all environments
- Rotate credentials regularly, especially for production

### Database Security

- Use dedicated database users with minimal required permissions
- Enable SSL connections for production databases
- Use different database names for each environment

### Email Security

- Use environment-specific email accounts to avoid conflicts
- Enable 2FA on email accounts used for SMTP
- Use app-specific passwords instead of main account passwords

### AWS Security

- Use IAM roles instead of access keys where possible
- Follow the principle of least privilege for S3 bucket permissions
- Enable S3 bucket versioning and logging

### Redis Security

- Use Redis AUTH in production
- Configure Redis to bind to specific interfaces only
- Enable TLS for Redis connections in production

## Troubleshooting

### Common Issues

1. **Database Connection Failed**
    - Verify database credentials and host accessibility
    - Check if PostgreSQL service is running
    - Ensure firewall allows connections on the specified port

2. **Email Not Sending**
    - Verify SMTP credentials and host settings
    - Check if less secure app access is enabled (for Gmail)
    - Ensure email host allows connections from your server IP

3. **Redis Connection Failed**
    - Verify Redis is running and accessible
    - Check Redis configuration and authentication
    - Ensure Redis host and port are correct

4. **AWS S3 Access Denied**
    - Verify AWS credentials are correct
    - Check S3 bucket permissions and policies
    - Ensure the bucket exists in the specified region

### Environment Variable Validation

To validate your environment configuration, you can use Django's management command:

```bash
uv run manage.py check --deploy
```

This will check for common configuration issues and security problems.

## Migration Between Environments

When moving from development to production:

1. **Update Database Settings**: Change from DEV_ to PRD_ prefixed variables
2. **Configure Production Email**: Set up production SMTP service
3. **Setup AWS S3**: Configure S3 for media file storage
4. **Enable Redis**: Configure Redis for production caching
5. **Update URLs**: Set production frontend URLs for password reset
6. **Security Review**: Ensure all credentials are production-ready

## Support

For environment configuration issues:

- Check the main project README for setup instructions
- Verify all required variables are set for your target environment
- Ensure environment prefixes match your deployment configuration
- Contact the development team for environment-specific questions