import axios from 'axios'
import { Device } from '../types'

export const client = axios.create({
  baseURL: '/',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
  // Ensure the browser sends HttpOnly session cookies to the backend
  withCredentials: true
})

// If the Vite env VITE_ADMIN_KEY is provided, include it on admin requests.
const meta: any = import.meta
const ADMIN_KEY_ENV = (meta.env && meta.env.VITE_ADMIN_KEY) || ''

// Allow runtime admin key from localStorage (set via UI)
let ADMIN_KEY_RUNTIME = ''
try{
  if (typeof localStorage !== 'undefined'){
    ADMIN_KEY_RUNTIME = localStorage.getItem('admin_key') || ''
  }
}catch(e){/* ignore */}

const INITIAL_ADMIN_KEY = ADMIN_KEY_ENV || ADMIN_KEY_RUNTIME
if (INITIAL_ADMIN_KEY){
  client.defaults.headers['X-ADMIN-KEY'] = INITIAL_ADMIN_KEY
}

export function setAdminKey(key: string | null){
  try{
    if (key){
      client.defaults.headers['X-ADMIN-KEY'] = key
      if (typeof localStorage !== 'undefined') localStorage.setItem('admin_key', key)
    }else{
      delete client.defaults.headers['X-ADMIN-KEY']
      if (typeof localStorage !== 'undefined') localStorage.removeItem('admin_key')
    }
  }catch(e){
    // ignore
  }
}

export default {
  async getDevices(): Promise<Device[]>{
    const r = await client.get('/admin/devices')
    return r.data.devices as Device[]
  },
  async setSelection(payload:{entity_id:string, allowed:boolean}){
    const r = await client.post('/admin/devices/select', payload)
    return r.data
  }
}
