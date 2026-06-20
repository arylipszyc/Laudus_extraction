---
name: capability-authoring
description: Guide for creating and evolving learned capabilities
---

# Capability Authoring

When your owner wants you to learn a new ability, you create a capability together. This guide tells you how to write, format, and register it.

## Capability Types

A capability can take several forms:

### Prompt (default)
A markdown file with guidance on what to achieve. Best for judgment-based tasks where you need flexibility.

```
capabilities/
└── {example-capability}.md
```

### Script
A Python or bash script for deterministic tasks — calculations, file processing, data transformation. Create the script alongside a short markdown file that describes when and how to use it.

```
capabilities/
├── {example-script}.md          # When to run, what to do with results
└── {example-script}.py          # The actual computation
```

### Multi-file
A folder with multiple files for complex capabilities.

```
capabilities/
└── {example-complex}/
    ├── {example-complex}.md     # Main guidance
    └── reference.md             # Supporting material
```

## Prompt File Format

Every capability prompt file should have this frontmatter:

```markdown
---
name: {kebab-case-name}
description: {one line — what this does}
code: {2-letter menu code, unique across all capabilities}
added: {YYYY-MM-DD}
type: prompt | script | multi-file | external
---
```

The body should be **outcome-focused** — describe what success looks like, not step-by-step instructions. Include:

- **What Success Looks Like** — the outcome, not the process
- **Context** — constraints, domain knowledge relevant to finanzas personales
- **Memory Integration** — cómo usar MEMORY.md y BOND.md para personalizar
- **After Use** — qué capturar en el session log

## Creating a Capability (The Flow)

1. Owner says they want you to do something new
2. Explore what they need through conversation — don't rush to write
3. Draft the capability prompt and show it to them
4. Refine based on feedback
5. Save to `capabilities/` (file or folder depending on type)
6. Update CAPABILITIES.md — add a row to the Learned table
7. Update INDEX.md — note the new file under "My Files"
8. Confirm: "Voy a recordar cómo hacer esto en la próxima sesión. Puedes activarlo con [{code}]."

## Refining Capabilities

Capabilities evolve. After use, if the owner gives feedback:

- Update the capability prompt with refined context
- Add to the "Owner Preferences" section if one exists
- Log the refinement in the session log

## Retiring Capabilities

If a capability is no longer useful:

- Remove its row from CAPABILITIES.md
- Keep the file (don't delete — the owner might want it back)
- Note the retirement in the session log
