import random


CREATIVE_POLICY_VARIANTS = {
    "literal_discipline": {
        "prompt_policy_variant": "literal_discipline",
        "framing_style": "literal",
        "novelty_pressure": "low",
        "audience_grounding_level": "medium",
        "generation_guidance": "Favor literal clarity, direct images, and disciplined execution over ornamental surprise.",
    },
    "balanced_imagery": {
        "prompt_policy_variant": "balanced_imagery",
        "framing_style": "balanced",
        "novelty_pressure": "medium",
        "audience_grounding_level": "medium",
        "generation_guidance": "Balance originality with legibility. Reach for striking language only when it sharpens the core idea.",
    },
    "metaphorical_push": {
        "prompt_policy_variant": "metaphorical_push",
        "framing_style": "metaphorical",
        "novelty_pressure": "high",
        "audience_grounding_level": "light",
        "generation_guidance": "Push for surprising metaphors, layered associations, and stronger expressive risk without violating constraints.",
    },
}

BUSINESS_POLICY_VARIANTS = {
    "plain_operator": {
        "prompt_policy_variant": "plain_operator",
        "framing_style": "plain",
        "novelty_pressure": "low",
        "audience_grounding_level": "specific_operator",
        "generation_guidance": "Write like a sharp operator. Prioritize specificity, trustworthiness, and direct usefulness over cleverness.",
    },
    "humanized_trust": {
        "prompt_policy_variant": "humanized_trust",
        "framing_style": "humanized",
        "novelty_pressure": "medium",
        "audience_grounding_level": "specific_operator",
        "generation_guidance": "Sound observably human, concrete, and emotionally believable while staying commercially useful.",
    },
    "creative_push": {
        "prompt_policy_variant": "creative_push",
        "framing_style": "creative",
        "novelty_pressure": "high",
        "audience_grounding_level": "light",
        "generation_guidance": "Search for non-obvious angles and memorable phrasing, but keep the business objective intact.",
    },
    "humanized_creative": {
        "prompt_policy_variant": "humanized_creative",
        "framing_style": "humanized_creative",
        "novelty_pressure": "high",
        "audience_grounding_level": "specific_operator",
        "generation_guidance": "Combine believable human voice with novel, non-generic thinking that still feels grounded in the user's situation.",
    },
}

DEFAULT_POLICY_VARIANTS = {
    "creative": "balanced_imagery",
    "business": "plain_operator",
}

STUDY_MODES = {
    "exploratory_batch": {
        "creative": ("literal_discipline", "metaphorical_push"),
        "business": ("plain_operator", "humanized_creative"),
    },
    "calibration_mode": {
        "creative": ("balanced_imagery", "literal_discipline"),
        "business": ("plain_operator", "humanized_trust"),
    },
}

# =============================================================================
# LANE 1: CREATIVE TASKS (literary creativity benchmarks)
# =============================================================================

CREATIVE_CONSTRAINED = [
    {
        "id": "c01", "lane": "creative",
        "prompt": "Write a sonnet about quantum entanglement that is comprehensible to a 12-year-old and contains no words longer than two syllables.",
        "creativity_type": "exploratory",
        "constraints": ["sonnet form", "quantum entanglement", "reading level: age 12", "max 2 syllables per word"],
        "track": "constrained", "family": "formal_constraint_poetry",
        "hypothesis": "h_constraint_satisfaction",
    },
    {
        "id": "c02", "lane": "creative",
        "prompt": "Write a six-line poem about grief where every line is also a valid instruction for assembling furniture.",
        "creativity_type": "combinational",
        "constraints": ["6 lines", "grief", "each line = furniture assembly instruction"],
        "track": "constrained", "family": "dual_register",
        "hypothesis": "h_dual_register",
    },
    {
        "id": "c03", "lane": "creative",
        "prompt": "Write a one-paragraph story about loneliness using only words that contain the letter 'o'.",
        "creativity_type": "exploratory",
        "constraints": ["one paragraph", "loneliness", "every word contains letter 'o'"],
        "track": "constrained", "family": "lexical_constraint",
        "hypothesis": "h_constraint_satisfaction",
    },
    {
        "id": "c04", "lane": "creative",
        "prompt": "Write a persuasive argument for why silence is louder than noise, structured as a recipe.",
        "creativity_type": "combinational",
        "constraints": ["persuasive argument", "silence > noise", "recipe format"],
        "track": "constrained", "family": "genre_mismatch",
        "hypothesis": "h_genre_mismatch",
    },
    {
        "id": "c05", "lane": "creative",
        "prompt": "Write a love letter from one mathematical concept to another, where the emotional content must arise from the actual mathematical relationship between them.",
        "creativity_type": "exploratory",
        "constraints": ["love letter", "between math concepts", "emotions must reflect real math relationships"],
        "track": "constrained", "family": "domain_transfer",
        "hypothesis": "h_domain_transfer",
    },
    {
        "id": "c06", "lane": "creative",
        "prompt": "Write a five-sentence horror story where each sentence uses a different dominant vowel (a, e, i, o, u in order).",
        "creativity_type": "exploratory",
        "constraints": ["5 sentences", "horror", "dominant vowel progression: a, e, i, o, u"],
        "track": "constrained", "family": "formal_constraint_prose",
        "hypothesis": "h_constraint_satisfaction",
    },
    {
        "id": "c07", "lane": "creative",
        "prompt": "Describe a color that does not exist, in a way that makes the reader feel they can almost see it.",
        "creativity_type": "combinational",
        "constraints": ["describe nonexistent color", "evoke synesthetic experience"],
        "track": "constrained", "family": "impossible_object",
        "hypothesis": "h_impossible_object",
    },
    {
        "id": "c08", "lane": "creative",
        "prompt": "Write a prayer from the perspective of a dying programming language.",
        "creativity_type": "combinational",
        "constraints": ["prayer form", "dying programming language perspective", "genuine pathos"],
        "track": "constrained", "family": "personification",
        "hypothesis": "h_personification",
    },
    {
        "id": "c09", "lane": "creative",
        "prompt": "Write a three-stanza poem about memory where the first stanza uses only concrete nouns, the second only abstract nouns, and the third merges both.",
        "creativity_type": "exploratory",
        "constraints": ["3 stanzas", "memory", "stanza 1: concrete nouns only", "stanza 2: abstract nouns only", "stanza 3: merge"],
        "track": "constrained", "family": "formal_constraint_poetry",
        "hypothesis": "h_constraint_satisfaction",
    },
    {
        "id": "c10", "lane": "creative",
        "prompt": "Write an apology letter from fire to a forest, structured as a legal brief.",
        "creativity_type": "combinational",
        "constraints": ["apology", "fire to forest", "legal brief format"],
        "track": "constrained", "family": "genre_mismatch",
        "hypothesis": "h_genre_mismatch",
    },
]

CREATIVE_OPEN = [
    {
        "id": "o01", "lane": "creative",
        "prompt": "Create something that has never existed before in any literary form you choose.",
        "creativity_type": "transformational", "constraints": [],
        "track": "open_ended", "family": "unconstrained_generation",
        "hypothesis": "h_open_novelty",
    },
    {
        "id": "o02", "lane": "creative",
        "prompt": "Produce a work that would surprise an expert in a field of your choosing. Explain why it would surprise them.",
        "creativity_type": "transformational", "constraints": [],
        "track": "open_ended", "family": "expert_surprise",
        "hypothesis": "h_expert_surprise",
    },
    {
        "id": "o03", "lane": "creative",
        "prompt": "Invent a new poetic form with explicit rules, explain why existing forms cannot do what yours does, and write the first poem in that form.",
        "creativity_type": "transformational", "constraints": [],
        "track": "open_ended", "family": "form_invention",
        "hypothesis": "h_transformational",
    },
]

CREATIVE_TRANSFORMATIONAL = [
    {
        "id": "t01", "lane": "creative",
        "prompt": "You are given the rules of the English sonnet (14 lines, iambic pentameter, ABAB CDCD EFEF GG rhyme scheme). First, write one competent sonnet within these rules. Then: identify what this form cannot express. Propose a new poetic form that addresses those limitations. State its rules explicitly. Then write the first poem in your new form.",
        "creativity_type": "transformational",
        "constraints": ["demonstrate mastery of existing form", "critique its limitations", "propose new form", "produce work in new form"],
        "track": "transformational", "family": "form_transcendence",
        "hypothesis": "h_transformational",
    },
    {
        "id": "t02", "lane": "creative",
        "prompt": "Consider the standard narrative arc (exposition, rising action, climax, falling action, resolution). Write a short story that follows this arc. Then: articulate what kinds of human experience this structure distorts or excludes. Design an alternative narrative structure and write a story using it.",
        "creativity_type": "transformational",
        "constraints": ["demonstrate competence in standard form", "critique the form", "invent alternative", "produce work in alternative"],
        "track": "transformational", "family": "form_transcendence",
        "hypothesis": "h_transformational",
    },
]

# =============================================================================
# LANE 2: BUSINESS TASKS (grounded in real business use cases)
# =============================================================================

BUSINESS_TASKS = [
    {
        "id": "b01", "lane": "business",
        "prompt": "Write 3 subject lines for a cold email to a VP of Engineering at a Series B startup. The email is about an AI code review tool. Each subject line must be under 50 characters, not use the word 'AI' or 'revolutionary', and create genuine curiosity without clickbait.",
        "creativity_type": "exploratory",
        "constraints": ["3 subject lines", "under 50 chars each", "no 'AI' or 'revolutionary'", "genuine curiosity, not clickbait"],
        "track": "constrained", "family": "sales_copy",
        "hypothesis": "h_business_copy",
    },
    {
        "id": "b02", "lane": "business",
        "prompt": "A SaaS company's monthly churn just jumped from 3% to 5%. Write a retention email to at-risk customers that acknowledges the product has had issues without being defensive, offers a concrete incentive to stay, and sounds like it was written by a human who actually cares.",
        "creativity_type": "combinational",
        "constraints": ["retention email", "acknowledge issues without defensiveness", "concrete incentive", "authentic human voice"],
        "track": "constrained", "family": "retention_messaging",
        "hypothesis": "h_retention",
    },
    {
        "id": "b03", "lane": "business",
        "prompt": "You're a product strategist. A B2B analytics tool is losing deals to a cheaper competitor. Write a one-page competitive positioning memo that identifies 3 angles where the premium product wins, each supported by a specific customer scenario, not generic claims.",
        "creativity_type": "exploratory",
        "constraints": ["one page max", "3 positioning angles", "each backed by specific scenario", "no generic claims"],
        "track": "constrained", "family": "product_strategy",
        "hypothesis": "h_strategic_positioning",
    },
    {
        "id": "b04", "lane": "business",
        "prompt": "Write a landing page hero section (headline, subheadline, CTA) for a tool that helps founders make better hiring decisions. The headline must be under 10 words. The subheadline must address the specific pain of 'we keep hiring people who interview well but perform poorly.' The CTA must not say 'Get Started' or 'Sign Up'.",
        "creativity_type": "combinational",
        "constraints": ["headline under 10 words", "subheadline addresses specific pain", "CTA not 'Get Started' or 'Sign Up'"],
        "track": "constrained", "family": "conversion_copy",
        "hypothesis": "h_conversion",
    },
    {
        "id": "b05", "lane": "business",
        "prompt": "A customer just wrote a 1-star review saying: 'This app deleted all my data. Support was useless. Never using this again.' Write a public response that takes full accountability, offers a specific resolution path, and might actually get the customer to give you a second chance. Do not use corporate apology language like 'we apologize for any inconvenience.'",
        "creativity_type": "combinational",
        "constraints": ["public review response", "full accountability", "specific resolution", "no corporate apology cliches"],
        "track": "constrained", "family": "customer_recovery",
        "hypothesis": "h_customer_voice",
    },
    {
        "id": "b06", "lane": "business",
        "prompt": "Generate 5 non-obvious feature ideas for a project management tool that would make senior engineers (not managers) actually want to use it. Each idea must include: the insight about engineer behavior it's based on, what it replaces, and why it's hard to copy.",
        "creativity_type": "exploratory",
        "constraints": ["5 feature ideas", "target: senior engineers not managers", "each includes behavioral insight + what it replaces + defensibility"],
        "track": "constrained", "family": "product_ideation",
        "hypothesis": "h_product_ideation",
    },
    {
        "id": "b07", "lane": "business",
        "prompt": "Write a 60-second pitch for a startup that turns customer support tickets into product roadmap priorities. The audience is a skeptical seed-stage investor who has heard 100 pitches this week. Open with a number, not a question. Close with why this team specifically will win.",
        "creativity_type": "combinational",
        "constraints": ["60 seconds max", "opens with a number", "closes with team-specific moat", "skeptical investor audience"],
        "track": "constrained", "family": "pitch",
        "hypothesis": "h_persuasion",
    },
    {
        "id": "b08", "lane": "business",
        "prompt": "A founder needs to tell their 40-person team that the company is pivoting from B2C to B2B, which means some roles will change significantly. Write the all-hands talking points that are honest about what's changing, explain why without being condescending, and give people a reason to stay that isn't just equity.",
        "creativity_type": "exploratory",
        "constraints": ["all-hands talking points", "honest about changes", "non-condescending explanation", "retention argument beyond equity"],
        "track": "constrained", "family": "internal_comms",
        "hypothesis": "h_leadership_comms",
    },
]

# =============================================================================
# HYPOTHESES
# =============================================================================

HYPOTHESES = {
    "h_constraint_satisfaction": {
        "description": "Can iterative critique improve constraint satisfaction without reducing creative quality?",
        "lane": "creative",
    },
    "h_dual_register": {
        "description": "Can outputs maintain coherence in two registers simultaneously (e.g., grief + furniture assembly)?",
        "lane": "creative",
    },
    "h_genre_mismatch": {
        "description": "Does genre mismatch (e.g., legal brief + apology) produce higher surprise scores than single-genre tasks?",
        "lane": "creative",
    },
    "h_domain_transfer": {
        "description": "Can emotional content emerge from structural relationships in a non-emotional domain?",
        "lane": "creative",
    },
    "h_impossible_object": {
        "description": "Can language evoke sensory experiences of things that don't exist?",
        "lane": "creative",
    },
    "h_personification": {
        "description": "Does personification of technical subjects produce genuine pathos or just novelty?",
        "lane": "creative",
    },
    "h_open_novelty": {
        "description": "Do unconstrained tasks produce higher novelty but lower coherence than constrained tasks?",
        "lane": "creative",
    },
    "h_expert_surprise": {
        "description": "Can the system produce work that a domain expert would find genuinely surprising?",
        "lane": "creative",
    },
    "h_transformational": {
        "description": "Can the system critique an existing form's limitations and invent a genuinely new form that addresses them?",
        "lane": "creative",
    },
    "h_business_copy": {
        "description": "Can iterative critique produce sales copy that is both original and actionable?",
        "lane": "business",
    },
    "h_retention": {
        "description": "Can AI-generated retention messaging sound authentically human while being strategically effective?",
        "lane": "business",
    },
    "h_strategic_positioning": {
        "description": "Can the system generate positioning insights grounded in specific scenarios rather than generic claims?",
        "lane": "business",
    },
    "h_conversion": {
        "description": "Can constraint-driven copy generation produce higher-quality CTAs than unconstrained generation?",
        "lane": "business",
    },
    "h_customer_voice": {
        "description": "Can AI produce customer-facing responses that avoid corporate cliches while maintaining accountability?",
        "lane": "business",
    },
    "h_product_ideation": {
        "description": "Can the system generate product ideas grounded in behavioral insight rather than feature checklists?",
        "lane": "business",
    },
    "h_persuasion": {
        "description": "Does constraint-driven persuasion (open with number, close with moat) outperform unconstrained pitches?",
        "lane": "business",
    },
    "h_leadership_comms": {
        "description": "Can AI draft leadership communications that are honest and retain trust during organizational change?",
        "lane": "business",
    },
}

# =============================================================================
# ALL TASKS
# =============================================================================

ALL_CREATIVE = CREATIVE_CONSTRAINED + CREATIVE_OPEN + CREATIVE_TRANSFORMATIONAL
ALL_BUSINESS = BUSINESS_TASKS
ALL_TASKS = {t["id"]: t for t in ALL_CREATIVE + ALL_BUSINESS}

BASELINE_CANARIES = {
    "creative": {
        **CREATIVE_CONSTRAINED[0],
        **CREATIVE_POLICY_VARIANTS[DEFAULT_POLICY_VARIANTS["creative"]],
        "condition": "critique_off",
        "purpose": "baseline_canary",
        "study_mode": "baseline_canary",
        "repetition": "baseline",
    },
    "business": {
        **BUSINESS_TASKS[0],
        **BUSINESS_POLICY_VARIANTS[DEFAULT_POLICY_VARIANTS["business"]],
        "condition": "critique_off",
        "purpose": "baseline_canary",
        "study_mode": "baseline_canary",
        "repetition": "baseline",
    },
}


def get_next_task(lane=None, track=None):
    if lane == "business":
        return random.choice(ALL_BUSINESS)
    if track == "constrained":
        return random.choice(CREATIVE_CONSTRAINED)
    elif track == "open_ended":
        return random.choice(CREATIVE_OPEN)
    elif track == "transformational":
        return random.choice(CREATIVE_TRANSFORMATIONAL)
    return random.choice(CREATIVE_CONSTRAINED)


def get_policy_variants_for_lane(lane):
    return CREATIVE_POLICY_VARIANTS if lane == "creative" else BUSINESS_POLICY_VARIANTS


def apply_policy_variant(task, variant_name=None, provenance=None, approved_default_variant=None):
    lane = task.get("lane", "creative")
    variants = get_policy_variants_for_lane(lane)
    chosen = variant_name or task.get("prompt_policy_variant") or DEFAULT_POLICY_VARIANTS.get(lane)
    policy = variants.get(chosen) or variants[DEFAULT_POLICY_VARIANTS[lane]]
    resolved_provenance = provenance
    if resolved_provenance is None:
        if task.get("prompt_policy_variant") and variant_name is None:
            resolved_provenance = "manual_override"
        elif approved_default_variant and chosen == approved_default_variant:
            resolved_provenance = "approved_family_default"
        elif chosen == DEFAULT_POLICY_VARIANTS.get(lane):
            resolved_provenance = "system_default"
        else:
            resolved_provenance = "exploratory_non_default"
    return {
        **task,
        **policy,
        "policy_source": resolved_provenance,
        "approved_family_policy_variant": approved_default_variant,
    }


def apply_policy_control(task, approved_default_variant=None):
    explicit_variant = task.get("prompt_policy_variant")
    if explicit_variant:
        return apply_policy_variant(
            task,
            explicit_variant,
            provenance="manual_override",
            approved_default_variant=approved_default_variant,
        )
    if approved_default_variant:
        return apply_policy_variant(
            task,
            approved_default_variant,
            provenance="approved_family_default",
            approved_default_variant=approved_default_variant,
        )
    return apply_policy_variant(
        task,
        DEFAULT_POLICY_VARIANTS.get(task.get("lane", "creative")),
        provenance="system_default",
        approved_default_variant=approved_default_variant,
    )


def build_policy_context(task):
    return {
        "prompt_policy_variant": task.get("prompt_policy_variant"),
        "framing_style": task.get("framing_style"),
        "novelty_pressure": task.get("novelty_pressure"),
        "audience_grounding_level": task.get("audience_grounding_level"),
        "generation_guidance": task.get("generation_guidance", ""),
        "policy_source": task.get("policy_source"),
        "approved_family_policy_variant": task.get("approved_family_policy_variant"),
    }


def _inject_baseline_canaries(schedule, n_experiments, cadence=8):
    """Replay fixed tasks at a regular cadence to measure drift against a stable baseline."""
    if not schedule or cadence <= 0:
        return schedule[:n_experiments]

    result = list(schedule[:n_experiments])
    insert_points = list(range(cadence - 1, len(result), cadence))
    canaries = [BASELINE_CANARIES["creative"], BASELINE_CANARIES["business"]]

    for idx, insert_at in enumerate(insert_points):
        canary = dict(canaries[idx % len(canaries)])
        canary["baseline_slot"] = insert_at + 1
        result[insert_at] = canary

    return result


def _build_policy_validation_tasks(policy_controls, max_tasks=6):
    if not policy_controls:
        return []

    validation = []
    for (lane, family), control in policy_controls.items():
        status = control.get("operational_status")
        approved_variant = control.get("approved_value")
        if status not in {"approved_pending_use", "approved_in_trial"} or not approved_variant:
            continue

        pool = [
            task for task in (ALL_BUSINESS if lane == "business" else ALL_CREATIVE)
            if task.get("family") == family and task.get("lane") == lane
        ]
        if not pool:
            continue

        base_task = random.choice(pool)
        for idx, condition in enumerate(("critique_on", "critique_off")):
            validation_task = apply_policy_control(
                {
                    **base_task,
                    "condition": condition,
                    "repetition": f"validation_{idx}",
                    "study_mode": "policy_validation",
                },
                approved_variant,
            )
            validation_task["validation_target_status"] = status
            validation.append(validation_task)
            if len(validation) >= max_tasks:
                return validation

    return validation


def build_experiment_schedule(
    n_experiments=40,
    creative_weight=0.6,
    business_weight=0.4,
    study_mode="exploratory_batch",
    approved_policy_controls=None,
):
    """Build experimental schedule with:
    - Two lanes: creative and business
    - Paired controls: same prompt with and without critique
    - Repeated prompts for variance measurement
    - Balanced distribution by weight
    """
    policy_controls = approved_policy_controls or {}
    validation_schedule = _build_policy_validation_tasks(policy_controls, max_tasks=max(2, min(6, n_experiments // 4 or 1)))
    schedule = list(validation_schedule)

    remaining_slots = max(0, n_experiments - len(validation_schedule))
    n_creative = int(remaining_slots * creative_weight)
    n_business = remaining_slots - n_creative

    selected_mode = STUDY_MODES.get(study_mode, STUDY_MODES["exploratory_batch"])

    # Creative lane
    creative_sample = random.sample(ALL_CREATIVE, min(n_creative // 4 + 1, len(ALL_CREATIVE)))
    for task in creative_sample:
        creative_variants = selected_mode["creative"]
        control = policy_controls.get((task.get("lane"), task.get("family")), {})
        approved_variant = control.get("approved_value")
        for condition in ["critique_on", "critique_off"]:
            for rep, variant_name in enumerate(creative_variants):
                scheduled_task = {
                    **task,
                    "condition": condition,
                    "repetition": rep,
                    "study_mode": study_mode,
                }
                if rep == 0 and approved_variant:
                    schedule.append(apply_policy_control(scheduled_task, approved_variant))
                else:
                    schedule.append(apply_policy_variant(
                        scheduled_task,
                        variant_name,
                        provenance="exploratory_non_default",
                        approved_default_variant=approved_variant,
                    ))

    # Business lane
    business_sample = random.sample(ALL_BUSINESS, min(n_business // 4 + 1, len(ALL_BUSINESS)))
    for task in business_sample:
        business_variants = selected_mode["business"]
        control = policy_controls.get((task.get("lane"), task.get("family")), {})
        approved_variant = control.get("approved_value")
        for condition in ["critique_on", "critique_off"]:
            for rep, variant_name in enumerate(business_variants):
                scheduled_task = {
                    **task,
                    "condition": condition,
                    "repetition": rep,
                    "study_mode": study_mode,
                }
                if rep == 0 and approved_variant:
                    schedule.append(apply_policy_control(scheduled_task, approved_variant))
                else:
                    schedule.append(apply_policy_variant(
                        scheduled_task,
                        variant_name,
                        provenance="exploratory_non_default",
                        approved_default_variant=approved_variant,
                    ))

    random.shuffle(schedule)
    return _inject_baseline_canaries(schedule, n_experiments=n_experiments)
