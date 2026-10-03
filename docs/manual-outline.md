# DOCX Manual Outline + Video Index

Deliverable: `AWS-AgentCore-Voice-Agent-Manual.docx`, starting from
**brand-new machine + brand-new AWS account** and ending with a **working
Canadian phone agent + tests + monitoring + cleanup**, with no undocumented
preconfiguration.

## Screenshot & command rules

* Every actionable step gets: **purpose → exact command → expected result →
  verification → real screenshot** (of the exact software version used).
* Command blocks are labelled: `WINDOWS CMD` | `WINDOWS POWERSHELL` |
  `LINUX/SERVER` | `AWS CLI` | `PYTHON`.
* Every placeholder is explained in a table: `[YOUR_AWS_REGION]`,
  `[YOUR_ACCOUNT_ID]`, `[YOUR_BUCKET_NAME]`, `[YOUR_AGENT_RUNTIME_ARN]`,
  `[YOUR_PHONE_NUMBER]`, `[YOUR_TABLE_NAME]`.
* A **version record** section pins: Python, AWS CLI, AgentCore CLI, Node.js,
  Docker, and every pinned Python package (from `pyproject.toml`).

## Numbered sections

1. Project Overview
2. Final Architecture
3. Prerequisites
4. Windows Development Environment
5. Python Installation
6. AWS CLI Installation
7. Node.js / AgentCore CLI Setup
8. AWS Account Configuration
9. IAM Configuration
10. AgentCore Setup
11. Python Project Setup
12. Dependency Installation
13. Configuration
14. LLM Configuration
15. Voice Configuration
16. S3 Skill Storage
17. Skill File Creation
18. Skill Router
19. Session Memory
20. DynamoDB
21. Logging
22. CloudWatch
23. Telephony
24. Canadian Phone Number
25. AgentCore Deployment
26. First Local Test
27. First AWS Test
28. First Phone Call
29. Skill Routing Test
30. Session Isolation Test
31. Concurrent Calls
32. Security Tests
33. Monitoring
34. Troubleshooting
35. Updating Skills
36. Updating Python Code
37. Updating Tests
38. Cost Management
39. Disaster Recovery
40. Complete Cleanup
41. Rebuilding From Zero
42. Developer Handover

## Example step entry (format every actionable step like this)

> **STEP 17.4 — Create the S3 skill bucket**
> *Purpose:* stores authorized skill files per agent namespace.
> *Command:* `aws s3 mb s3://[YOUR_BUCKET_NAME] --region [YOUR_AWS_REGION]`
> *Expected result:* no output, exit code 0.
> *Verification:* `aws s3 ls` lists the bucket.
> *Screenshot:* `screenshots/17-4-s3-bucket-created.png` (real, current version).

## Video requirements

* Narrated MP4s numbered **identically** to the manual sections.
* Must show the *actual* work: terminal, AWS console, Python/AWS CLI install,
  AgentCore configuration, deployment, phone configuration, skill upload,
  tests, logs, security tests, cleanup — **no hidden preparation**.
* One video explicitly demonstrates:

  ```
  Agent A → allowed:  property_123.txt      ✔
  Agent A → attempt:  agent_B/secret.txt    ✘ ACCESS DENIED
  Session A: "My name is Peter."
  Session B: "What is my name?"             ✘ B does not know Peter
  ```

## Video Timestamp Index (fill actual times during recording)

| Manual section | Video time |
|---|---|
| 1. Project Overview | 00:00:00 |
| 3. Prerequisites | 00:04:15 |
| 4. Windows Development Environment | 00:11:32 |
| 5–7. Python / AWS CLI / Node setup | 00:18:40 |
| 8–9. AWS account + IAM | 00:25:10 |
| 10. AgentCore Setup | 00:31:48 |
| 11–13. Project + dependencies + configuration | 00:40:05 |
| 14–15. LLM + voice configuration | 00:49:30 |
| 16–17. S3 skill storage + skill files | 01:05:20 |
| 18. Skill Router | 01:14:00 |
| 19–22. Session memory, DynamoDB, logging, CloudWatch | 01:22:45 |
| 23–24. Telephony + Canadian number | 01:41:15 |
| 25–28. Deploy, first local/AWS test, first phone call | 01:55:00 |
| 29–31. Routing, isolation, concurrent calls | 02:10:30 |
| 32. Security tests | 02:18:44 |
| 33–34. Monitoring + troubleshooting | 02:30:00 |
| 35–37. Updating skills/code/tests | 02:42:00 |
| 38–41. Cost, DR, cleanup, rebuild from zero | 02:55:00 |
| 42. Developer handover | 03:10:00 |

## Final acceptance checklist (must be demonstrated, not claimed)

Voice: Canadian number · incoming call · natural conversation · streaming ·
interruption · correct audio.
Intelligence: intent · routing · ambiguity · correction · switching · no
hallucinated property data.
Memory: caller context within session · name retained · no cross-session memory.
Security: agent/file/IAM/session isolation · injection resistance · path
traversal protection.
Infra: AgentCore · S3 · DynamoDB · CloudWatch · IAM · telephony.
Testing: unit · integration · voice · concurrency · security · regression.
Docs: complete DOCX · real screenshots · exact commands/versions ·
troubleshooting · cost · cleanup.
Training: code walkthrough · skill modification · Python modification · test
modification · deployment modification.
