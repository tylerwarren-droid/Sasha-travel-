import { agapi } from './agapi'
import { sasha } from './sasha'
import { ad } from './ad'
import { campusme } from './campusme'
import { relocation } from './relocation'
import { spain } from './spain'

export const TABS = [agapi, sasha, ad, campusme, relocation, spain] as const
export { agapi, sasha, ad, campusme, relocation, spain }
