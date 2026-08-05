import { Turn, Option } from './viewer/Canvas.jsx'
import LandingA from './wireframes/landing/LandingA.jsx'
import LandingB from './wireframes/landing/LandingB.jsx'
import LandingC from './wireframes/landing/LandingC.jsx'
import LandingD from './wireframes/landing/LandingD.jsx'
import ModelPage from './wireframes/pages/ModelPage.jsx'
import DiscoveriesPage from './wireframes/pages/DiscoveriesPage.jsx'
import CaseStudiesPage from './wireframes/pages/CaseStudiesPage.jsx'

export default function App() {
  return (
    <>
      <Turn
        id="t1"
        name="MetricCage portfolio, reimagined in Paper wireframe — four landing-page structures"
        next="1a and 1b are verbatim from the export. 1c was truncated mid-section and its case-study strip and contact footer are reconstructed; 1d was missing from the export entirely and is reconstructed from its description."
      >
        <Option id="1a" label="Broadcast scroll — the current narrative, redrawn" width={640}>
          <LandingA />
        </Option>
        <Option id="1b" label="Dashboard — sidebar nav, evidence as a control room" width={680}>
          <LandingB />
        </Option>
        <Option
          id="1c"
          label="Editorial column — one narrow thread, numbers as headlines"
          note="tail reconstructed"
          width={520}
        >
          <LandingC />
        </Option>
        <Option
          id="1d"
          label="Bento grid — the whole argument above the fold"
          note="reconstructed"
          width={720}
        >
          <LandingD />
        </Option>
      </Turn>

      <Turn
        id="t2"
        name="The rest of the site — the three inner pages in the same system"
        next="Derived from the live pages rather than the export, which only covers the landing page. Section eyebrows and headings are the live site's own; runtime-computed headings are left as bars."
      >
        <Option id="2a" label="Model evidence — model.html" note="derived" width={640}>
          <ModelPage />
        </Option>
        <Option id="2b" label="Discoveries — discoveries.html" note="derived" width={640}>
          <DiscoveriesPage />
        </Option>
        <Option id="2c" label="Case studies — case-studies.html" note="derived" width={640}>
          <CaseStudiesPage />
        </Option>
      </Turn>
    </>
  )
}
