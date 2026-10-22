import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { OpenSourceAcknowledgements } from '../ui/OpenSourceAcknowledgements.tsx'

test('the acknowledgements page renders both package names', () => {
  const html = renderToStaticMarkup(
    createElement(OpenSourceAcknowledgements, { onBack: () => {} }),
  )
  assert.match(html, /Open-source acknowledgements/)
  assert.match(html, />certifi</)
  assert.match(html, /MPL-2\.0/)
  assert.match(html, /https:\/\/github\.com\/certifi\/python-certifi/)
  assert.match(html, />@capgo\/native-purchases</)
  assert.match(html, /https:\/\/github\.com\/Cap-go\/capacitor-native-purchases/)
})
