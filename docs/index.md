# MkPFS documentation

<div class="hero-grid">
  <div class="hero-card hero-card--accent">
    <p class="eyebrow">PlayStation file-system tooling</p>
    <h1>Build, check, and inspect PFS images with a curated knowledge base.</h1>
    <p>
      MkPFS documents the command-line tool itself and the wider PFS / PKG research
      trail that informed it. The site is designed to grow into a full reference hub
      with screenshots, diagrams, and source-backed notes.
    </p>
    <div class="hero-actions">
      <a class="md-button md-button--primary" href="getting-started/">Get started</a>
      <a class="md-button" href="knowledge/">Explore the knowledge base</a>
      <a class="md-button md-button--secondary" href="https://github.com/sponsors/RenanGBarreto">Sponsor</a>
    </div>
  </div>
  <div class="hero-card">
    <h2>What the site covers</h2>
    <ul>
      <li>mkpfs install, create, check, and ls usage</li>
      <li>Source-backed knowledge pages for PFS and PKG material</li>
      <li>Planned screenshots, diagrams, and workflow notes</li>
    </ul>
  </div>
</div>

```mermaid
flowchart LR
    A[Input folder] --> B[mkpfs create]
    B --> C[PFS image]
    C --> D[mkpfs check]
    C --> E[mkpfs ls]
    F[Knowledge sources] --> G[Docs pages]
    G --> H[Search + navigation]
```

## Start here

1. Read [Getting Started](getting-started.md) for install and first-run commands.
2. Open [Commands](commands/index.md) for the live CLI reference.
3. Visit [Knowledge Base](knowledge/index.md) for the longer-form PFS / PKG material.

## Sponsor

If the project is useful to you, support it on GitHub Sponsors so the docs and tool can keep moving.
