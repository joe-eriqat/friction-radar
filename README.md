# friction-radar
AI-powered onboarding intelligence from public customer sentiment.

Friction Radar analyzes public customer sentiment from sources like Reddit, app reviews, and community posts to identify where users succeed or fail during onboarding. It clusters feedback into onboarding success points, friction points, confusion moments, churn risks, and recommended product fixes.

Early-stage teams often do not know why users fail to activate and not all data is captured during onboarding. Feedback is scattered across Reddit, app stores, review sites, and support channels. Manually reading this feedback is slow, biased, and hard to translate into concrete onboarding improvements.

Friction Radar turns raw public sentiment into an onboarding intelligence report. Given a product, category, competitor, or pasted review data, it extracts user sentiment, clusters onboarding-related themes, scores friction severity, and recommends changes to improve activation.


## Features

- Public sentiment ingestion from pasted reviews, Reddit comments, or app-store-style feedback
- AI clustering of onboarding success and failure patterns
- Detection of activation blockers, confusion points, expectation mismatches, and churn signals
- Identification of positive onboarding moments and product strengths
- Severity and frequency scoring for each theme
- Evidence-backed summaries with representative user quotes
- Actionable onboarding recommendations
- Exportable report view for screenshots and stakeholder sharing

## How It Works

1. Enter a product, competitor, or product category.
2. Paste public feedback or load a sample dataset.
3. Friction Radar classifies each comment by sentiment, onboarding stage, and user intent.
4. The system clusters related feedback into success and failure themes.
5. It generates a prioritized onboarding report with evidence and recommendations.

## Output Categories

Friction Radar organizes feedback into:

### Success Points
Moments where users express clarity, delight, fast activation, trust, or immediate value.

Examples:
- Users understand the core value quickly
- Setup feels fast or guided
- A competitor’s onboarding is praised
- Users describe a “magic moment”

### Failure Points
Moments where users express confusion, abandonment, frustration, distrust, or unmet expectations.

Examples:
- Users do not understand what to do first
- Setup requires too many steps
- Pricing or limits are unclear
- The product promise does not match the first experience
- Users compare the onboarding poorly to competitors

### Churn / Drop-off Signals
Language that suggests users may abandon the product.

Examples:
- “I gave up”
- “Too much setup”
- “Not worth it”
- “I could not figure out…”
- “I switched back to…”

## Example Use Case

A founder building an AI note-taking app wants to understand why users fail to activate. They paste Reddit comments and app reviews about competing AI note-taking tools. Friction Radar identifies that users love fast transcription and automatic summaries, but often fail during calendar permissions, bot setup, pricing discovery, and workspace sharing.

The report recommends a guided setup checklist, sample meeting demo, clearer permission explanations, and earlier pricing transparency.


## Example Output

| Theme | Type | Severity | Evidence | Recommendation |
|---|---|---:|---|---|
| Setup feels unclear | Failure Point | High | Users say they do not know what to connect first | Add a 3-step onboarding checklist |
| Fast first summary creates delight | Success Point | High | Users praise receiving value immediately after upload | Move sample summary earlier in onboarding |
| Pricing surprise causes distrust | Failure Point | Medium | Users complain about limits appearing too late | Show plan limits before signup completion |
| Competitor has smoother activation | Failure Point | High | Users mention switching because setup was easier elsewhere | Add demo mode before requiring integrations |

## Tech Stack

- Frontend: Next.js / React
- Backend: Next.js API routes or FastAPI
- AI: LLM-based classification and summarization
- Data: Sample public feedback dataset, pasted text, or CSV upload
- Storage: Local JSON or SQLite

## Getting Started

```bash
git clone <repo-url>
cd friction-radar
npm install
npm run dev

## Demo Mode

The project includes a sample dataset of public-style customer feedback so the app can be demonstrated without live scraping, customer data, or external integrations.

Demo flow:

1. Load the sample dataset.
2. Run onboarding sentiment analysis.
3. View success and failure clusters.
4. Open the generated onboarding report.
5. Screenshot the prioritized recommendations.

## Limitations

- The current prototype uses pasted or sample public feedback rather than full automated scraping.
- Sentiment analysis is directional and should be validated with real user interviews or product analytics.
- Theme frequency depends on the quality and representativeness of the input data.
- The tool is designed for onboarding research, not as a replacement for analytics instrumentation.

## Future Work

- Live connectors for Reddit, App Store reviews, G2, Chrome Web Store, and support tickets
- Competitor comparison across onboarding success and failure points
- Churn-risk detection from user language
- Auto-generated onboarding experiments
- Integration with product analytics tools
- Export to Linear, Notion, or Jira
- Ad and landing-page copy generation based on user pain language
