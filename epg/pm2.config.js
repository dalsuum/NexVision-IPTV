const grab = 'npm run grab -- --channels=channels.xml --output=public/guide.xml'

const apps = [
  {
    name: 'epg-serve',
    script: 'npx serve -- public',
    instances: 1,
    watch: false,
    autorestart: true,
    env: {
      PORT: 3000
    }
  },
  {
    name: 'epg-grab',
    script: `npx chronos -e "${grab}" -p "0 */6 * * *" -l`,
    instances: 1,
    watch: false,
    autorestart: true
  },
  {
    name: 'epg-grab-startup',
    script: grab,
    instances: 1,
    autorestart: false,
    watch: false,
    max_restarts: 1
  }
]

module.exports = { apps }
