# CloudScale AI — Company Profile

## Mission Statement

CloudScale AI empowers engineering teams to build, train, and deploy AI workloads at any scale — from weekend side-projects to Fortune 500 production pipelines — without managing infrastructure. We believe world-class AI compute should be accessible, predictable, and blazing fast.

---

## Company Overview

| Field            | Details                                      |
|------------------|----------------------------------------------|
| **Founded**      | 2021, San Francisco, CA                      |
| **Team Size**    | 180 employees (65% engineering)              |
| **Stage**        | Series B — $62M raised                      |
| **Customers**    | 4,200+ companies across 38 countries         |
| **Uptime SLA**   | 99.95% (Compute Engine), 99.99% (Storage API)|

---

## Target Audience

### Primary Segments

1. **AI/ML Engineers**
   - Training large language models and diffusion models
   - Need burst compute on demand without long-term commitments
   - Pain point: GPU availability and cold-start latency on incumbent clouds

2. **Startups & Scale-Ups**
   - Building AI-native products (chatbots, recommendation engines, vision APIs)
   - Need cost-predictable pricing that scales with revenue
   - Pain point: unpredictable bills from major cloud providers

3. **Enterprise Data Science Teams**
   - Running scheduled batch inference jobs and data pipelines
   - Need compliance (SOC 2 Type II, GDPR), audit logs, VPC peering
   - Pain point: lack of governance tooling on GPU clouds

4. **Independent Researchers & Academia**
   - Access to affordable A100/H100 clusters for research
   - Benefit from our Academic Grant Program (up to $5,000 credits/year)

---

## Core Services

### 1. Compute Engine
High-performance GPU and CPU instances for AI workloads.
- GPU fleet: NVIDIA H100, A100 (80 GB), A10G, RTX 4090
- CPU fleet: AMD EPYC 9004 series, up to 192 cores
- Bare-metal and containerized options
- Auto-scaling groups with sub-60-second spin-up

### 2. Storage API
S3-compatible object storage purpose-built for AI datasets and model artifacts.
- Global CDN with 28 edge PoPs
- Tiered pricing: Hot, Warm, Archive
- Built-in dataset versioning and lineage tracking
- Max single object size: 5 TB

### 3. Model Registry
Private artifact store for model checkpoints and ONNX exports.
- Semantic versioning with rollback
- Integrated with Compute Engine for zero-copy deployment

### 4. Inference Gateway
Managed endpoint hosting with autoscaling and canary deployments.
- Cold start < 800 ms (warm pool enabled by default)
- Request batching and adaptive concurrency control
- gRPC + REST dual protocol support

### 5. Observability Suite
Real-time metrics, GPU utilisation heatmaps, cost attribution dashboards.
- Prometheus-compatible metrics export
- Anomaly detection alerts via PagerDuty / Slack / email
- 90-day log retention on all plans

---

## Pricing Philosophy

- **Pay-as-you-go**: billed per second of GPU/CPU utilisation
- **Reserved Instances**: 1-year or 3-year commitments (up to 45% discount)
- **Spot Instances**: up to 80% cheaper, best-effort availability
- **Free Tier**: $50 credit on sign-up, no credit card required

Plans: **Starter** | **Growth** | **Business** | **Enterprise (custom)**

---

## Support Tiers

| Tier       | Response SLA    | Channels                         |
|------------|-----------------|----------------------------------|
| Community  | Best-effort     | Docs, Discord                    |
| Standard   | 24 hours        | Email, Web Form                  |
| Business   | 4 hours         | Email, Live Chat, WhatsApp       |
| Enterprise | 1 hour (24/7)   | Dedicated Slack, Phone, On-site  |

---

## Compliance & Security

- SOC 2 Type II certified
- GDPR & CCPA compliant
- ISO 27001 in progress (Q3 2026)
- Data residency options: US, EU, APAC
- Private VPC peering available on Business+ plans
- All data encrypted at rest (AES-256) and in transit (TLS 1.3)
