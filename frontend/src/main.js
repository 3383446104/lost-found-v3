import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/theme.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import App from './App.vue'
import router from './router'

// 全局消息弹窗配置：精简提醒，不阻塞操作
ElMessage.defaults = {
  duration: 2000,
  showClose: true,
  max: 2,
  grouping: true,
  offset: 60
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: undefined })  // Element Plus 中文将在后续配置

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 等首次导航（含会话校验）完成后再挂载：
// 避免路由守卫还在校验令牌时，App 已经用 START_LOCATION 的默认 meta 渲染出布局
router.isReady().catch(() => {}).then(() => app.mount('#app'))
