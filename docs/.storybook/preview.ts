import type { Preview } from "@storybook/react"

import { getThemeStore } from "./addon-theme/themeStore"
import { CustomDocsContainer, WithTheme } from "./components/StorybookApp"
import "./preview.css"

const preview: Preview = {
  parameters: {
    options: {
      storySort: {
        // Storybook statically parses this value and requires an inline literal.
        // docs/scripts/check-docs.mjs keeps it aligned with docsNavigation.ts.
        order: [
          "Overview",
          ["Introduction", "How specx works", "Quickstart", "Choose a workflow"],
          "Tutorial",
          ["Build your first core feature"],
          "Guides",
          [
            "Install agent skills",
            "Initialize a project",
            "Add core behavior",
            "Add persistence",
            "Add FastAPI delivery",
            "Compose dependencies",
            "Configure settings and logging",
            "Test a service",
            "Adopt specx in an existing service",
          ],
          "Concepts",
          [
            "Architecture boundaries",
            "Use cases, services, and capabilities",
            "Ports and adapters",
            "Transactions and units of work",
            "Testing strategy",
            "Policy ownership",
          ],
          "Reference",
          [
            "CLI",
            "Configuration",
            "Architecture rules",
            "Foundation API",
            "Architecture Python API",
            "Skills catalog",
            "Generated project",
            "Troubleshooting",
            "Glossary",
            "Contributing",
          ],
        ],
      },
    },
    docs: {
      container: CustomDocsContainer,
      toc: {
        contentsSelector: ".sbdocs-content",
        headingSelector: "h2, h3",
        ignoreSelector: ".sbdocs-subtitle, .specx-card h3",
        title: "",
      },
    },
  },
  decorators: [WithTheme],
  initialGlobals: {
    theme: getThemeStore(),
  },
}

export default preview
