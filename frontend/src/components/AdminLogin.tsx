import React, {useState, useEffect} from 'react'
import { client, setAdminKey } from '../services/api'

export default function AdminLogin(){
  const [key, setKey] = useState<string>('')
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(()=>{
    // do not prefill key from localStorage for security; leave blank
  },[])

  async function save(){
    setError(null)
    try{
  const res = await fetch('/admin/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({admin_key: key}), credentials: 'include' })
      if (res.status === 200){
        // server sets httponly cookie for session
        try{ window.dispatchEvent(new Event('admin_key_saved')) }catch(e){}
        try{ window.dispatchEvent(new Event('admin_key_valid')) }catch(e){}
        setVisible(false)
        setError(null)
      } else {
        setError('De API key is onjuist of geen toegang. Controleer en probeer opnieuw.')
      }
    }catch(e){
      setError('Kan geen verbinding maken met de server om de key te valideren.')
    }
  }

  async function clear(){
    setKey('')
    try{ await fetch('/admin/logout', { method: 'POST' }) }catch(e){}
    try{ window.dispatchEvent(new Event('admin_key_saved')) }catch(e){}
    try{ window.dispatchEvent(new Event('admin_key_invalid')) }catch(e){}
  }

  return (
    <div>
      <button onClick={()=>setVisible(v=>!v)} style={{marginLeft:12}}>{visible? 'Close':'Admin'}</button>
      {visible && (
        <div style={{position:'absolute',right:20,top:56,background:'#fff',padding:12,borderRadius:8,boxShadow:'0 4px 12px rgba(0,0,0,0.08)'}}>
          <div style={{marginBottom:8}}>Admin API key</div>
          <input value={key} onChange={e=>setKey(e.target.value)} style={{width:320,padding:6}} />
          {error && <div style={{color:'#8b0000',marginTop:8}}>{error}</div>}
          <div style={{marginTop:8,display:'flex',gap:8}}>
            <button onClick={save}>Save</button>
            <button onClick={clear}>Clear</button>
          </div>
        </div>
      )}
    </div>
  )
}
