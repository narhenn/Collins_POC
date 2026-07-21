// EVScenario.jsx — the EV "Simulate" page. Mission Control (the ported scenario-engine
// builder + simulator) is the primary experience; the existing GoalCert scenario/faults
// + training page is kept alongside it under a second tab.
import React, { useState } from 'react'
import EVSimulate from './EVSimulate.jsx'
import Scenario from './Scenario.jsx'
import { Icon } from './lib.jsx'

export default function EVScenario(props) {
  const [tab, setTab] = useState('sim')
  return (
    <div className="evsc">
      <div className="evsc-tabs">
        <button className={tab === 'sim' ? 'on' : ''} onClick={() => setTab('sim')}>
          <Icon n="ti-brain" /> Mission Control
        </button>
        <button className={tab === 'faults' ? 'on' : ''} onClick={() => setTab('faults')}>
          <Icon n="ti-urgent" /> Faults &amp; Training
        </button>
      </div>
      {tab === 'sim' ? <EVSimulate /> : <Scenario {...props} />}
    </div>
  )
}
