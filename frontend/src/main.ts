import { createApp } from 'vue'
import { createPinia } from 'pinia'

import './assets/main.css'

import App from './App.vue'
import router from './router'
import { useActivityStore } from './stores/activity'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// Badges count days the app was opened (any page), so record today once on load
useActivityStore(pinia).markOpenedToday()

app.mount('#app')
