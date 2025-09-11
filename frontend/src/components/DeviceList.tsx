import React, {useEffect, useState} from 'react'
import { Device } from '../types'
import api from '../services/api'
import { getIconForEntity } from '../icons'

export default function DeviceList() {
  const [devices, setDevices] = useState<Device[]>([])
  const [filter, setFilter] = useState<string>('')
  const [isAdmin, setIsAdmin] = useState<boolean>(false)
  const [layoutMode, setLayoutMode] = useState<'relaxed'|'compact'>(() => {
    try{ return (localStorage.getItem('deviceList.layout') as 'relaxed'|'compact') || 'relaxed' }catch(e){ return 'relaxed' }
  })
  const [showAllowedOnly, setShowAllowedOnly] = useState<boolean>(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load(){
    setLoading(true)
    try{
      setError(null)
      const res = await api.getDevices()
      setDevices(res)
      // successful load implies admin session/header was valid
      setIsAdmin(true)
      try{ window.dispatchEvent(new Event('admin_key_valid')) }catch(e){}
    }catch(e){
      console.error(e)
      const status = (e as any)?.response?.status
      if (status === 401){
        setError('Geen toestemming om apparaten te laden — klik rechtsboven op Admin en voer de API key in')
        setIsAdmin(false)
        try{ window.dispatchEvent(new Event('admin_key_invalid')) }catch(e){}
      }else{
        setError('Fout bij het laden van apparaten, controleer server logs')
      }
    }finally{setLoading(false)}
  }

  useEffect(()=>{ load() }, [])

  useEffect(()=>{
    try{ localStorage.setItem('deviceList.layout', layoutMode) }catch(e){}
  },[layoutMode])

  const filtered = devices.filter(d => {
    if (showAllowedOnly && !d.allowed) return false
    const q = filter.trim().toLowerCase()
    if (!q) return true
    return (d.friendly_name || '').toLowerCase().includes(q) || d.entity_id.toLowerCase().includes(q)
  })

  useEffect(()=>{
    // Reload when admin key is saved in the Admin UI
    const handler = () => { load() }
    window.addEventListener('admin_key_saved', handler)
    // update admin validity when events fire
    const okHandler = () => setIsAdmin(true)
    const invalidHandler = () => setIsAdmin(false)
    window.addEventListener('admin_key_valid', okHandler)
    window.addEventListener('admin_key_invalid', invalidHandler)
    return () => {
      window.removeEventListener('admin_key_saved', handler)
      window.removeEventListener('admin_key_valid', okHandler)
      window.removeEventListener('admin_key_invalid', invalidHandler)
    }
  }, [])

  async function toggle(entity_id:string, allowed:boolean){
    try{
      await api.setSelection({entity_id, allowed})
      setDevices(d=>d.map(x=> x.entity_id===entity_id ? {...x, allowed} : x))
    }catch(e){
      console.error(e)
      alert('Failed to save selection')
    }
  }

  return (
  <div className={`device-list layout-${layoutMode}`}>
      <div className="controls" style={{display:'flex',gap:8,alignItems:'center'}}>
        <input placeholder="Zoek apparaat (naam of entity)" value={filter} onChange={e=>setFilter(e.target.value)} style={{padding:8,borderRadius:8,border:'1px solid #e5e7eb',width:320}} disabled={!isAdmin} title={!isAdmin ? 'Admin key vereist om te filteren' : ''} />
        <label style={{display:'flex',alignItems:'center',gap:6}} title={!isAdmin ? 'Admin key vereist' : ''}>
          <input type="checkbox" checked={showAllowedOnly} onChange={e=>setShowAllowedOnly(e.target.checked)} disabled={!isAdmin} />
          <span style={{fontSize:13}}>Toon alleen actieve (toegelaten)</span>
        </label>
    <button onClick={()=>setLayoutMode(l=> l==='relaxed' ? 'compact' : 'relaxed')} title="Toggle layout" style={{padding:'6px 10px',borderRadius:6,border:'1px solid #e5e7eb',background:'#fff'}}>Weergave: {layoutMode === 'relaxed' ? 'Relaxed' : 'Compact'}</button>
        <button onClick={load} disabled={loading}>{loading? 'Refreshing...':'Refresh'}</button>
      </div>

      {error && (
        <div style={{padding:12,background:'#fff5f5',border:'1px solid #ffc9c9',borderRadius:6,marginBottom:12}}>
          <strong>{error}</strong>
          <div style={{marginTop:6}}>Klik op de <em>Admin</em>-knop rechtsboven en voer de Admin API key in.</div>
        </div>
      )}

      <div className="grid">
        {filtered.map(d=> (
          <div key={d.entity_id} className="card">
            <div className="icon-col" title={`mdi:${getIconForEntity(d.entity_id, d.device_class).mdi}`}>
              <div className="icon-emoji">{getIconForEntity(d.entity_id, d.device_class).emoji}</div>
            </div>
            <div className="meta">
              <div className="meta-row">
                <div className="name">{d.friendly_name || d.entity_id}</div>
                <div className="state-badge">{String(d.state)}</div>
              </div>
              <div className="entity"><code className="entity-value" title={d.entity_id}>{d.entity_id}</code></div>
            </div>
            <div className="toggle">
              <label className="switch" title="Allow for Google Home sync">
                <input aria-label={`Allow ${d.entity_id}`} type="checkbox" checked={!!d.allowed} onChange={(e)=>toggle(d.entity_id, e.target.checked)} />
                <span className="slider"></span>
              </label>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
