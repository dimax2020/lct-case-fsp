import { publicSession } from '../../utils/public-session'

export default defineEventHandler((event) => publicSession(event))
