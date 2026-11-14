# HackPrinceton Fall 2026 — Best Practical AI Innovation (Amazon)

**Track research and OpenArms implications**  
**Prepared:** November 14, 2026  
**Evidence basis:** Official track description supplied by the team; sponsor/judge Discord posts and LinkedIn advice supplied by the team; independently verified historical HackPrinceton results.  
**Status:** Research reference, not an official rulebook. Explicit requirements and quoted sponsor advice are separated from our interpretation.

---

# Part I — Amazon Track Research

## 1. Track overview

**Prize:** Best Practical AI Innovation — by Amazon  
**Central challenge:** Build AI that solves a meaningful problem for real people. Amazon explicitly wants tools that go beyond staged demonstrations: applications that **reason, plan, take action, adapt**, and are useful enough for a person to return to.

The track is **domain-agnostic**. Healthcare, sustainability, accessibility, finance, education, logistics, and other domains are welcomed. The user-provided description includes examples ranging from shopping agents and logistics optimizers to gesture/voice accessibility systems and multi-agent research tools. **Those examples are suggestions, not required categories or architectures.**

### Sponsor's concise framing

Aymane Omari, an Amazon mentor and judge at HackPrinceton Fall 2026, wrote in the event Discord:

> “Build AI that someone would use every day, not AI that only works in a demo.”

> “We want tools that reason, plan, take action and adapt.”

He added that the strongest projects take multistep actions, learn from context or feedback, and make AI feel simple to use. He invoked Amazon's principles **Customer Obsession**, **Think Big**, and **Invent and Simplify**.

**Interpretation:** A polished, working user journey matters at least as much as the conceptual sophistication of the model. A complicated architecture with little genuine user value is not automatically strong.

## 2. Official judging rubric — equally weighted

| Criterion | Weight | What Amazon explicitly asks | What a judge could reasonably look for (interpretation) |
|---|---:|---|---|
| **Creativity** | **25%** | Original idea; clever or surprising approach | Distinct insight, not just a standard chatbot or wrapper |
| **Usefulness** | **25%** | Real problem that users care about | Clear target user, concrete pain point, compelling repeated-use scenario |
| **Technical implementation** | **25%** | Well-built, reliable, technically sound | Successful live execution, sensible architecture, error handling, grounded results |
| **User experience** | **25%** | Intuitive, polished, worth using again | Short path from intent to outcome, readable state/feedback, manageable friction |

**Important:** These are the *only stated numerical weights*. Agentic behavior, adaptation, real-world impact, and good design are emphasized in the track description but are **not separately listed as additional weighted categories**. Do not invent a fifth criterion or assume an explicit requirement to run multiple agents.

## 3. What a submission must include

The supplied track rules list four required deliverables:

1. **Working prototype / demo**
2. **Clear use case and target user**
3. **Basic documentation**
4. **Presentation / pitch**

The track expressly permits any combination of:

- Open-source AI tools, libraries, and frameworks
- AI APIs (LLM, search, data, vision, speech, etc.)
- Custom models or fine-tuned systems
- Agentic frameworks and tool-use integrations
- Existing services or infrastructure, including Amazon platforms

**AWS is not mandatory.** The Discord guidance says AWS services such as Bedrock and SageMaker are options, while a separate Amazon Discord message states **AWS credits are not being offered for this hackathon**. A project should use AWS only if it provides a tangible benefit within its development budget and timeline. Historical winners using Amazon Nova do not establish a platform-use requirement for 2026.

## 4. Advice directly from Aymane (former winner, now mentor/judge)

Aymane says he won Amazon's GenAI prize while hacking at HackPrinceton 2024, and is back at Fall 2026 to mentor and judge. The team provided these three takeaways from a LinkedIn post recounting his advice:

### A. Start with the problem and work backward

Define **who the user is** and **what they need** before choosing technology. Build the simplest experience that solves the problem. A smaller, carefully executed project can be more persuasive than technically impressive machinery without a clear use case.

### B. Ask mentors for feedback early

Invite criticism of your assumptions before the architecture is locked. Aymane's quoted phrasing:

> “Feedback is a gift, but it's mostly data.”

Use feedback as evidence to evaluate, not a mandate to implement every suggestion.

### C. Do not over-index on winning

The judge's perspective is subjective; build something worth keeping and learn from the people around you. His quoted line about his own winning weekend:

> “It still (genuinely) wasn't the best part of the weekend.”

**How this informs the track:** This advice is strong sponsor-adjacent product guidance, but not a separate formal scoring system.

## 5. Historical precedents (context, not Fall 2026 rules)

### Fall 2025 — Amazon Best Practical AI Innovation

Jamie Brown's Amazon HackPrinceton 2025 recap publicly named:

| Project | What it did | Relevant lesson — interpretation |
|---|---|---|
| **ViralWave** | AI content-generation workflow drawing on trending social-media signals and Nova Act orchestration | Converts messy input data into a user-facing deliverable |
| **Cropit** | Agricultural analytics combining real-world farm information with regenerative-agriculture and profitability insights | Grounds AI in an industry-specific, practical decision |
| **MindPad** | Multimodal educational workspace using gestures, voice, computer vision, and AI; also a Best Overall winner | Makes complex AI interaction tangible and accessible |

These are **previous-year awardees**, not a template or a claim that the same judges will prefer the same features this year. A University of Illinois report independently confirms MindPad earned Best Practical AI Innovation by Amazon alongside other awards.

### Fall 2024 — Amazon GenAI challenge

Aymane Omari's team won for **SustainAI**, an AI-assisted sustainability companion that gave personalized, data-driven recommendations based on user context. His public write-up describes real-time tailored suggestions and an OpenAI-powered conversational interface. This was **a different, earlier Amazon prize**, so it is instructive about user framing rather than proof of the current rubric.

## 6. What is confirmed versus not confirmed

| Confirmed by supplied sponsor rules / comments | Not established by the available evidence |
|---|---|
| Four scoring dimensions worth 25% each | A mandatory multi-agent architecture |
| Working prototype, user, documentation, and pitch required | A minimum number of tool calls, models, or agent steps |
| Any application domain is eligible | A requirement to use AWS, Amazon Nova, or Bedrock |
| Agentic behavior and contextual adaptation are strongly encouraged | That a robot must autonomously execute every action |
| Amazon will not provide AWS credits | A guaranteed scoring advantage for any particular cloud provider |
| Aymane is mentoring and judging | Aymane's advice replacing or superseding the published rubric |

## 7. A practical submission checklist

- [ ] State the user and pain point in one clear sentence.
- [ ] Show an end-to-end task with a successful observable outcome.
- [ ] Explain what decisions AI actually makes (not merely where a model API is called).
- [ ] Demonstrate a meaningful adaptation to context, feedback, or state, if implemented.
- [ ] Make the interface legible: input, plan/action, progress, result, and recovery.
- [ ] Verify the critical path works repeatedly; include a credible fallback demo.
- [ ] Document architecture, setup, limitations, and what is simulated versus physical.
- [ ] Prepare a concise pitch centered on user problem → workflow → outcome → evidence.
- [ ] Seek feedback from Amazon mentors before locking in the final pitch.

---

# Part II — OpenArms: Applicability and Strategy

> **Project context used here:** OpenArms is a robotics / physical-AI concept for hands-free or more accessible laboratory tasks, involving a robotic arm and AI-mediated instructions. Specific capabilities, hardware reliability, target audience, and final feature scope are **not assumed to be complete**.

## 1. Does OpenArms fit this track?

**Yes, conceptually.** Robotics is not a requirement, but Amazon explicitly mentions **accessibility using voice, vision, or gesture** as one possible application. OpenArms can also fit through its intended laboratory workflow and ability to take action in the physical world.

**Fit is not the same as competitiveness.** If the final system only maps a command such as “move left” to a predefined motor function, the demonstration may satisfy an AI-plus-hardware story but give weaker evidence for Amazon's repeated emphasis on **planning, multistep execution, adaptation, practical value, and ease of use**.

## 2. Decide on the primary user (not yet a confirmed project decision)

Possible user framing to validate with mentors or user research:

- **Lab learner:** Someone learning to perform repeatable, structured procedures who benefits from guided robotic assistance.
- **Researcher/technician:** Someone who wants to issue higher-level instructions for simple, repetitive bench tasks.
- **Person with mobility or dexterity limitations:** Someone for whom certain bench interactions may be difficult without assistance.

Do **not** claim that the system is accessible to a defined disability population or suitable for real laboratory deployment without testing. Pick **one primary user** for the pitch and describe what concrete problem the current prototype actually solves.

## 3. Evaluate OpenArms against Amazon's 25% / 25% / 25% / 25% rubric

| Criterion | Potential OpenArms strength | Main risk | Evidence to produce |
|---|---|---|---|
| **Creativity (25%)** | Physical task execution connected to high-level language/AI reasoning | Generic voice-controlled robotic arms already exist | Specific lab workflow and a distinct user insight |
| **Usefulness (25%)** | Hands-free support for a repeatable real task | Contrived use case or no defined user | Clear persona, task frequency, why existing alternatives fall short |
| **Technical (25%)** | Integration across perception / planning / tool calls / control | Hardware unreliability, hallucinated actions, weak observability | Repeatable successful task; constrained action API; visible state checks |
| **UX (25%)** | Natural-language goal rather than low-level motion controls | User must babysit every command or interpret raw debug logs | Clean goal input, progress steps, confirmation, errors/recovery |

**No numerical score is assigned here.** The table maps opportunities and risks, not measured project performance.

## 4. One useful agentic workflow (proposed, not implemented)

**User goal:** “Help me transfer a small amount of colored water from container A to container B.” Use benign demo materials; do not present this as validated chemical handling.

1. **Interpret the goal:** Parse the requested outcome, objects, and constraints.
2. **Check context:** Retrieve known hardware capabilities and any available scene/sensor state.
3. **Plan:** Select a sequence of **allowed, tested** skills, such as locate, move, grasp, tilt, return.
4. **Request approval where warranted:** Confirm actions with spill or collision risk, depending on the demo's safety architecture.
5. **Execute:** Call bounded robot-control tools, not unrestricted model-generated motor commands.
6. **Observe and adapt:** Use available feedback to confirm an action or choose a safe recovery/stop.
7. **Report:** Show completion status, actions taken, and uncertainty or limitations.

This sequence demonstrates how Amazon's “reason, plan, take action and adapt” language **could** map to OpenArms. It is not a demand to implement every step or a recommendation to make the LLM the low-level controller. It is better to have fewer reliably working steps than an ambitious but unstable flow.

## 5. Minimum credible demo versus stretch goals

**Minimum credible version:** A user selects or states a meaningful task, AI determines a sequence from a **small, verified action library**, the arm executes at least one observable physical result, and the UI makes progress and outcome understandable. Be explicit about anything simulated or manually assisted.

**Higher-value stretch:** The system checks one relevant piece of feedback (e.g., target location or action success) and **changes its next step** instead of blindly replaying a fixed sequence.

**Avoid during the hackathon unless already proven:** Unbounded novel motion generation, claims of autonomous safe chemical handling, general-purpose laboratory competence, or elaborate multi-agent orchestration that adds latency and failure modes without user benefit.

## 6. How to communicate value to an Amazon judge

**Problem:** Who is this for, and what bench task is cumbersome, inaccessible, or too low-level to instruct manually?  
**Solution:** The user specifies the *outcome*, not individual motor actions.  
**Intelligence:** Show a concrete planning or adaptation decision.  
**Execution:** Demonstrate the arm accomplishing a real, bounded action.  
**UX:** Show simple controls, legible progress, and safe failure behavior.  
**Scope:** Explain exactly what works and what is experimental.

Example **provisional** positioning (edit after validating user and implementation):

> “OpenArms lets a lab user describe a simple bench task in natural language. Rather than requiring them to script individual arm movements, it translates that goal into verified robot actions, tracks progress, and reports what happened.”

Do not use this as a claim of working functionality until the demo verifies it.

## 7. Track-specific decisions

- **Prioritize the user problem over architecture.** This directly follows Aymane's first tip.
- **Treat physical hardware as a differentiator, not the whole value proposition.** Amazon evaluates usefulness and UX just as heavily as implementation.
- **Keep dependencies tight.** AWS is optional and credits are unavailable; framework choice should follow demonstrated needs.
- **Build a repeatable demo.** A failed live manipulation may undermine both technical quality and UX; choose a small, reliable task over theatrical complexity.
- **Solicit early sponsor feedback.** Show a working vertical slice and ask whether the real-user value is legible.

## 8. Distinction from the LangChain Deep Agents prize

LangChain's prize asks for a *meaningful application of its Deep Agents harness*; its representative emphasized context management, delegation/fan-out, synthesis, and not forcing unnecessary features. Amazon's prize **does not prescribe a framework** and publishes a broader, explicitly balanced scoring rubric. The same OpenArms build could be eligible for both, but what you emphasize is different:

- **For LangChain:** Why Deep Agents is genuinely necessary and how it orchestrates tasks.
- **For Amazon:** Why a real user wants the result, how AI acts/adapts, whether the build is reliable, and whether the experience is intuitive.

**Overall interpretation:** OpenArms has plausible alignment with the Amazon track, but its strongest Amazon submission will be a **small, reliable, end-to-end experience aimed at a specific user**, with clear evidence of agentic decision-making—not the greatest possible number of AI features.

---

# Sources and provenance

## Primary current-event material supplied by the team

1. **HackPrinceton Fall 2026, Amazon “Best Practical AI Innovation” track description and evaluation criteria.** Supplied in the team's chat, including exact 25%-each rubric and submission requirements.
2. **Aymane Omari, event Discord message.** Supplied in the team's chat; describes customer obsession, multistep/action/adaptation, judging, permitted tools, and his mentor/judge role. [Aymane's LinkedIn profile](https://www.linkedin.com/in/aymane-omari/).
3. **Amazon event Discord follow-up.** Supplied in the team's chat: AWS credits are not available for this hackathon.
4. **LinkedIn advice about Aymane (Jamie Brown post).** Three tips supplied verbatim by the team. [User-shared LinkedIn URL](https://www.linkedin.com/posts/jamiechbrown_hackprinceton-amazon-amazonnova-share-7524515149756522497-kTX0/). The page could not be fetched directly during this review; the three tips therefore rely on the user's supplied text, rather than independent confirmation of the linked page.

## Independently checked public historical sources

5. [Jamie Brown — Amazon at HackPrinceton Fall 2025 recap](https://www.linkedin.com/posts/jamiechbrown_definetomorrow-amazonatprinceton-hackprinceton2025-activity-7393696464054673408-OTfE) — identifies ViralWave, Cropit, and MindPad as awardees.
6. [University of Illinois — MindPad / HackPrinceton coverage](https://siebelschool.illinois.edu/news/golcha-hackprinceton) — independent report that MindPad received Best Practical AI Innovation by Amazon.
7. [Jamie Brown — Amazon at HackPrinceton Fall 2024 recap](https://www.linkedin.com/posts/jamiechbrown_definetomorrow-amazonatprinceton-activity-7262927147244077056-6_QG) — identifies the earlier Amazon GenAI winners.
8. [Aymane Omari — SustainAI project recap](https://www.linkedin.com/posts/aymane-omari_genai-mlh-matlab-activity-7261840912459165698-KQ5y) — describes the past winning product and its personalization approach.
9. [HackPrinceton Fall 2026 official site](https://www.hackprinceton.com/) — event and sponsor context.

**Documentation discipline:** Quotes in this file come from user-provided Discord/LinkedIn text; public sources provide historical context. Proposed OpenArms workflows and judging implications are analyses, not sponsor promises, proven prototype functions, or official judging requirements.
