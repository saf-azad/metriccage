import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// Paper design tokens, copied verbatim from the design system. Order matters: fonts,
// then values, then the thin element defaults that consume them.
import './styles/tokens/fonts.css'
import './styles/tokens/colors.css'
import './styles/tokens/typography.css'
import './styles/tokens/geometry.css'
import './styles/tokens/spacing.css'
import './styles/tokens/motion.css'
import './styles/tokens/base.css'
import './styles/canvas.css'

import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
