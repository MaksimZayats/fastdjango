export type DocsPage = {
  path: string
  title: string
}

export type DocsSection = {
  pages: readonly DocsPage[]
  title: string
}

export const docsNavigation = [
  {
    title: "Overview",
    pages: [
      { title: "Introduction", path: "overview-introduction" },
      { title: "How specx works", path: "overview-how-specx-works" },
      { title: "Quickstart", path: "overview-quickstart" },
      { title: "Choose a workflow", path: "overview-choose-a-workflow" },
    ],
  },
  {
    title: "Tutorial",
    pages: [
      { title: "Build your first core feature", path: "tutorial-build-your-first-core-feature" },
    ],
  },
  {
    title: "Guides",
    pages: [
      { title: "Install agent skills", path: "guides-install-agent-skills" },
      { title: "Initialize a project", path: "guides-initialize-a-project" },
      { title: "Add core behavior", path: "guides-add-core-behavior" },
      { title: "Add persistence", path: "guides-add-persistence" },
      { title: "Add FastAPI delivery", path: "guides-add-fastapi-delivery" },
      { title: "Compose dependencies", path: "guides-compose-dependencies" },
      {
        title: "Configure settings and logging",
        path: "guides-configure-settings-and-logging",
      },
      { title: "Test a service", path: "guides-test-a-service" },
      {
        title: "Adopt specx in an existing service",
        path: "guides-adopt-specx-in-an-existing-service",
      },
    ],
  },
  {
    title: "Concepts",
    pages: [
      { title: "Architecture boundaries", path: "concepts-architecture-boundaries" },
      {
        title: "Use cases, services, and capabilities",
        path: "concepts-use-cases-services-and-capabilities",
      },
      { title: "Ports and adapters", path: "concepts-ports-and-adapters" },
      {
        title: "Transactions and units of work",
        path: "concepts-transactions-and-units-of-work",
      },
      { title: "Testing strategy", path: "concepts-testing-strategy" },
      { title: "Policy ownership", path: "concepts-policy-ownership" },
    ],
  },
  {
    title: "Reference",
    pages: [
      { title: "CLI", path: "reference-cli" },
      { title: "Configuration", path: "reference-configuration" },
      { title: "Architecture rules", path: "reference-architecture-rules" },
      { title: "Foundation API", path: "reference-foundation-api" },
      { title: "Architecture Python API", path: "reference-architecture-python-api" },
      { title: "Skills catalog", path: "reference-skills-catalog" },
      { title: "Generated project", path: "reference-generated-project" },
      { title: "Troubleshooting", path: "reference-troubleshooting" },
      { title: "Glossary", path: "reference-glossary" },
      { title: "Contributing", path: "reference-contributing" },
    ],
  },
] as const satisfies readonly DocsSection[]

export const docsPages: DocsPage[] = []

for (const section of docsNavigation) {
  for (const page of section.pages) {
    docsPages.push(page)
  }
}

export const docsHref = (path: string) => {
  const sectionSeparator = path.indexOf("-")

  if (sectionSeparator === -1) {
    throw new Error(`Documentation path must include a section: ${path}`)
  }

  return `/docs/${path.slice(0, sectionSeparator)}/${path.slice(sectionSeparator + 1)}/`
}
