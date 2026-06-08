// FileDropZone.jsx — A drag-and-drop file upload area.
//
// The user can either drag files onto this box or click it to open a file picker.
// Once files are selected, they appear in a list below the drop zone with an
// "×" button to remove each one.
//
// Props:
//   files   (File[])         — currently selected files (controlled by the parent component)
//   onChange (fn)            — called with the new file array whenever files are added/removed
//   accept  (string)         — file-type filter for the native file picker (e.g. ".pdf,.docx")
//   multiple (boolean)       — whether multiple files can be selected at once
//   label   (string)         — descriptive text inside the drop zone
//   hint    (string)         — smaller hint text below the label

import { useRef, useState } from 'react'

export default function FileDropZone({
  files = [],
  onChange,
  accept = '',
  multiple = true,
  label = 'Drop files here or click to browse',
  hint = '',
}) {
  // dragging tracks whether the user is currently dragging a file over the zone.
  // When true, we add the 'dragging' CSS class to change the box appearance.
  const [dragging, setDragging] = useState(false)

  // inputRef lets us programmatically click the hidden <input type="file"> element
  // when the user clicks anywhere on the visible drop zone box.
  const inputRef = useRef(null)

  // addFiles is called with a FileList (from drag or input).
  // It merges new files with existing ones, avoiding duplicates by name+size.
  function addFiles(newFiles) {
    const merged = [...files]
    for (const f of newFiles) {
      // Only add if no existing file has the same name and size
      if (!merged.find(e => e.name === f.name && e.size === f.size)) {
        merged.push(f)
      }
    }
    onChange(merged)   // tell the parent component about the updated file list
  }

  // removeFile removes one file from the list by its array index.
  function removeFile(idx) {
    onChange(files.filter((_, i) => i !== idx))
  }

  // handleDrop fires when the user releases dragged files onto the zone.
  function handleDrop(e) {
    e.preventDefault()           // prevent the browser from opening the file
    setDragging(false)           // reset the drag-highlight style
    addFiles(e.dataTransfer.files)  // e.dataTransfer.files = the dropped file(s)
  }

  return (
    <div>
      {/* The visible drop zone box — clicking it triggers the hidden file input */}
      <div
        className={`drop-zone ${dragging ? 'dragging' : ''}`}
        role="button"
        tabIndex={0}
        aria-label="File upload area"
        onClick={() => inputRef.current?.click()}
        onKeyDown={e => e.key === 'Enter' && inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        {/* Cloud/upload icon */}
        <div style={{ fontSize: 32, color: '#1b3a6b' }}>📂</div>

        {/* Main instruction text — uses <strong> so "Drop files here" is bold */}
        <p><strong>{label}</strong></p>

        {/* Smaller hint text, e.g. "Accepts .pdf, .docx, ..." */}
        {hint && <p>{hint}</p>}
      </div>

      {/* Hidden file input — this is what actually opens the OS file picker.
          It is invisible; we trigger it by calling inputRef.current.click() above. */}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        style={{ display: 'none' }}
        onChange={e => addFiles(e.target.files)}   // e.target.files = selected files
      />

      {/* List of already-selected files, each with a remove button */}
      {files.length > 0 && (
        <ul className="file-list" aria-label="Selected files">
          {files.map((f, i) => (
            <li key={`${f.name}-${f.size}`}>
              {/* File name + size in human-readable form */}
              <span>{f.name} <span style={{ color: '#888' }}>({(f.size / 1024).toFixed(1)} KB)</span></span>

              {/* × button to remove this file from the list */}
              <button
                type="button"
                onClick={() => removeFile(i)}
                aria-label={`Remove ${f.name}`}
              >×</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
