// App.jsx — The root of the entire React application.
// React renders components like nested HTML blocks.  This file is the outermost
// "shell": it owns the two-tab layout and decides which tab is visible.
// Everything the user sees lives somewhere inside this component tree.

import { useState } from 'react'          // useState lets a component remember things between renders

import Header        from './components/Header.jsx'                        // The dark-blue EPA banner at the top
import Scanner508Tab from './components/scanner-508/Scanner508Tab.jsx'    // Tab 1: 508 / WCAG compliance scanner
import UrlCheckerTab from './components/url-checker/UrlCheckerTab.jsx'    // Tab 2: Dead-link URL checker

// The list of tabs shown in the navigation bar.
// 'id' is used internally; 'label' is the text the user reads.
const TABS = [
  { id: 'scanner508', label: '508 Compliance Scanner' },
  { id: 'urlchecker', label: 'URL Checker' },
]

export default function App() {
  // activeTab stores which tab is currently selected.
  // useState('scanner508') means it starts on the first tab by default.
  // When the user clicks a different tab, setActiveTab updates this value,
  // and React automatically re-renders the page to show the new tab's content.
  const [activeTab, setActiveTab] = useState('scanner508')

  return (
    // The outer <div> is an invisible wrapper — React requires a single root element.
    <div>
      {/* Header renders the blue EPA banner; it receives no data from here */}
      <Header />

      {/* Tab navigation bar — one button per entry in the TABS array */}
      <nav className="tab-bar" role="tablist" aria-label="Tool tabs">
        {TABS.map(tab => (
          // For each tab definition, create a <button>.
          // The 'active' CSS class is added only when this tab is currently selected
          // (tab.id === activeTab), which makes it visually highlighted.
          <button
            key={tab.id}
            role="tab"
            aria-selected={tab.id === activeTab}
            className={tab.id === activeTab ? 'active' : ''}
            onClick={() => setActiveTab(tab.id)}   // clicking switches the active tab
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Tab content area — only the matching tab component is rendered */}
      <main className="tab-content" role="tabpanel">
        {/* Short-circuit evaluation: if activeTab equals 'scanner508',
            render the Scanner508Tab component; otherwise render nothing for it */}
        {activeTab === 'scanner508' && <Scanner508Tab />}
        {activeTab === 'urlchecker' && <UrlCheckerTab />}
      </main>
    </div>
  )
}
