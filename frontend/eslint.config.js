import js from '@eslint/js'
import { defineConfig, globalIgnores } from 'eslint/config'
import prettier from 'eslint-config-prettier'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default defineConfig([
  // Generated or vendored code is not linted by our rules.
  globalIgnores(['dist', 'src/types/api.generated.ts', 'src/components/ui']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      jsxA11y.flatConfigs.recommended,
      prettier,
    ],
    languageOptions: { ecmaVersion: 2023, globals: globals.browser },
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/ban-ts-comment': [
        'error',
        { 'ts-ignore': true, 'ts-expect-error': 'allow-with-description' },
      ],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      // Request text and LLM output are untrusted: never render them as HTML.
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'dangerouslySetInnerHTML is banned: request and LLM text is untrusted.',
        },
      ],
      // All network calls go through src/lib/api-client.ts.
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: 'Use the API client in src/lib/api-client.ts.' },
      ],
      // A feature may only be imported through its index.ts.
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/features/*/*'],
              message: 'Import a feature only through its index.ts (e.g. "@/features/requests").',
            },
          ],
        },
      ],
    },
  },
  {
    files: ['src/lib/api-client.ts'],
    rules: { 'no-restricted-globals': 'off' },
  },
])
