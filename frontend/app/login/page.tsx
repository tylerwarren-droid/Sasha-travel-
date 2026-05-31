'use client'
import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase'
import { useRouter } from 'next/navigation'

export default function LoginPage() {
  const [status, setStatus] = useState('Connecting to demo...')
  const router = useRouter()
  const supabase = createClient()

  useEffect(() => {
    const login = async () => {
      const { error } = await supabase.auth.signInWithPassword({
        email: 'demo@luxurioustraveler.com',
        password: 'demo123'
      })
      if (error) {
        setStatus('Error: ' + error.message)
      } else {
        router.push('/')
        router.refresh()
      }
    }
    login()
  }, [])

  return (
    <div style={{minHeight:'100vh',background:'#0a0a0f',display:'flex',alignItems:'center',justifyContent:'center',flexDirection:'column',gap:'16px'}}>
      <div style={{width:'40px',height:'40px',borderRadius:'12px',background:'linear-gradient(135deg,#6366f1,#9333ea)',display:'flex',alignItems:'center',justifyContent:'center',color:'#fff',fontWeight:'bold',fontSize:'18px'}}>S</div>
      <div style={{color:'rgba(255,255,255,0.5)',fontSize:'14px',fontFamily:'system-ui'}}>{status}</div>
    </div>
  )
}
