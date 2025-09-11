import React, {useEffect, useState} from 'react'
import DeviceList from './components/DeviceList'
import AdminLogin from './components/AdminLogin.tsx'

export default function App(){
  const [adminOk, setAdminOk] = useState<boolean>(() => {
    try{ return !!localStorage.getItem('admin_key') }catch(e){ return false }
  })

  useEffect(()=>{
    const ok = ()=>setAdminOk(true)
    const invalid = ()=>setAdminOk(false)
    window.addEventListener('admin_key_valid', ok)
    window.addEventListener('admin_key_invalid', invalid)
    return ()=>{
      window.removeEventListener('admin_key_valid', ok)
      window.removeEventListener('admin_key_invalid', invalid)
    }
  }, [])

  return (
    <div className="container">
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center'}}>
        {adminOk ? (
          <div className="header">
            <h1>Home Assistant → Google Home</h1>
          </div>
        ) : (
          <div />
        )}
        {/* Admin button always visible so user can enter API key */}
        <AdminLogin />
      </div>

      {adminOk && (
        <p>Vink apparaten aan die met Google Home gesynchroniseerd mogen worden.</p>
      )}

      <DeviceList />
    </div>
  )
}
