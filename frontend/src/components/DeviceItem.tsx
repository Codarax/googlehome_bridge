import React from 'react'
import { Device } from '../types'

export default function DeviceItem({device, onToggle}:{device:Device,onToggle:(id:string,allowed:boolean)=>void}){
  return (
    <tr>
      <td><input type="checkbox" checked={!!device.allowed} onChange={e=>onToggle(device.entity_id,e.target.checked)} /></td>
      <td>{device.entity_id}</td>
      <td>{device.friendly_name}</td>
      <td>{String(device.state)}</td>
    </tr>
  )
}
