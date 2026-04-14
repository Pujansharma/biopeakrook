# AWS ECS Networking — VPC & Load Balancer Setup

Reference for deploying ECS Fargate tasks in private subnets behind an Application Load Balancer.

---

## VPC Settings

### Private Subnets

- ECS tasks run in **private subnets** — no public IP assigned to tasks.
- Use at least **two private subnets** across two Availability Zones for service redundancy.
- Variable: `PRIVATE_SUBNET_ID_1`, `PRIVATE_SUBNET_ID_2`

### Public Subnets

- Used exclusively for the **ALB** and **NAT Gateway**.
- Must have an **Internet Gateway** attached and a route `0.0.0.0/0 → IGW` in the route table.
- Variable: `PUBLIC_SUBNET_ID_1`, `PUBLIC_SUBNET_ID_2`

### NAT Gateway

- Deploy one NAT Gateway **per AZ** inside a public subnet, each with an Elastic IP.
- Variables: `NAT_GATEWAY_ID_AZ1`, `NAT_GATEWAY_ID_AZ2`, `ELASTIC_IP_AZ1`, `ELASTIC_IP_AZ2`
- Without a NAT Gateway (or VPC endpoints), tasks in private subnets cannot reach ECR, CloudWatch, or Secrets Manager.

### VPC Endpoints (alternative to NAT Gateway, or use both)

Required interface endpoints when tasks have no internet route:

| Endpoint | Purpose |
|---|---|
| `com.amazonaws.REGION.ecr.dkr` | Pull Docker images from ECR |
| `com.amazonaws.REGION.ecr.api` | ECR API calls |
| `com.amazonaws.REGION.logs` | CloudWatch Logs (awslogs driver) |
| `com.amazonaws.REGION.secretsmanager` | Secrets Manager (if used) |
| `com.amazonaws.REGION.ssm` | SSM Parameter Store (if used) |

**Gateway endpoint** (free, no security group needed):

| Endpoint | Purpose |
|---|---|
| `com.amazonaws.REGION.s3` | ECR image layer storage |

- All interface endpoints need **Enable Private DNS** turned on.
- VPC must have **DNS resolution** and **DNS hostnames** both enabled.

### Security Groups

**ECS Task SG** (`SG_ECS_TASK`):

| Direction | Protocol | Port | Source/Destination |
|---|---|---|---|
| Inbound | TCP | `CONTAINER_PORT` (8000) | `SG_ALB` only |
| Outbound | TCP | 443 | `0.0.0.0/0` (ECR, CloudWatch, etc.) |

**VPC Endpoint SG** (`SG_VPC_ENDPOINT`):

| Direction | Protocol | Port | Source/Destination |
|---|---|---|---|
| Inbound | TCP | 443 | `PRIVATE_SUBNET_CIDR` |

**ALB SG** (`SG_ALB`):

| Direction | Protocol | Port | Source/Destination |
|---|---|---|---|
| Inbound | TCP | 80 | `0.0.0.0/0` |
| Inbound | TCP | 443 | `0.0.0.0/0` |
| Outbound | TCP | `CONTAINER_PORT` (8000) | `SG_ECS_TASK` |

### Route Tables

**Public subnet route table:**

| Destination | Target |
|---|---|
| `VPC_CIDR` | local |
| `0.0.0.0/0` | `IGW_ID` |

**Private subnet route table:**

| Destination | Target |
|---|---|
| `VPC_CIDR` | local |
| `0.0.0.0/0` | `NAT_GATEWAY_ID` |
| `pl-XXXXX` (S3 prefix list) | `S3_GATEWAY_ENDPOINT_ID` |

---

## Load Balancer Settings

### Target Group (`TG_NAME`)

| Setting | Value |
|---|---|
| Target type | IP (required for Fargate) |
| Protocol | HTTP |
| Port | `CONTAINER_PORT` (8000) |
| VPC | `VPC_ID` |
| Health check protocol | HTTP |
| Health check path | `/health/` or `/` |
| Health check port | traffic port (8000) |
| Healthy threshold | 2 |
| Unhealthy threshold | 3 |
| Timeout | 5s |
| Interval | 30s |
| Success codes | `200` |

> The target group speaks **HTTP to port 8000** — TLS is terminated at the ALB, not at the container. Do not set the target group protocol to HTTPS unless the container itself serves TLS.

### ALB Listeners

Standard flow: client hits HTTPS → ALB terminates TLS → forwards plain HTTP to container.

```
Client
  │
  ▼ HTTPS :443
ALB (SG_ALB)
  │  TLS terminated here (ACM_CERTIFICATE_ARN)
  ▼ HTTP :8000
ECS Task (SG_ECS_TASK)
```

**Listener 1 — HTTP :80**
- Action: Redirect to HTTPS :443 (301)

**Listener 2 — HTTPS :443**
- Certificate: `ACM_CERTIFICATE_ARN` (must be in the same region as the ALB)
- Action: Forward to `TG_NAME`

### IAM — ECS Task Execution Role (`TASK_EXECUTION_ROLE_ARN`)

Required for the task to start and log:

```
ecr:GetAuthorizationToken          — resource: *
ecr:BatchCheckLayerAvailability    — resource: ECR_REPO_ARN
ecr:GetDownloadUrlForLayer         — resource: ECR_REPO_ARN
ecr:BatchGetImage                  — resource: ECR_REPO_ARN
logs:CreateLogGroup                — resource: LOG_GROUP_ARN
logs:CreateLogStream               — resource: LOG_GROUP_ARN:*
logs:PutLogEvents                  — resource: LOG_GROUP_ARN:*
secretsmanager:GetSecretValue      — resource: SECRET_ARN (if injecting secrets)
ssm:GetParameters                  — resource: SSM_PARAM_ARN (if using Parameter Store)
```

Shortcut: attach `AmazonECSTaskExecutionRolePolicy` — covers ECR and CloudWatch Logs.

### Health Check — Common Failure Causes

1. **`SG_ECS_TASK` blocks port 8000 from `SG_ALB`** — most common cause.
2. **Target group protocol set to HTTPS** but container serves plain HTTP.
3. **Health check path returns non-2xx** — ensure the path exists and responds without auth.
4. **Container port mismatch** — task definition `containerPort` must equal target group port.
5. **Task in private subnet, no NAT/endpoints** — task fails to pull image and never becomes healthy.
