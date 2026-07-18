"""Планировщик автообновления модели"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from model import load_matches_data, train_models, save_model, BotConfig

logger = logging.getLogger(__name__)

class ModelScheduler:
    def __init__(self, config: BotConfig):
        self.scheduler = AsyncIOScheduler()
        self.config = config
        
    async def update_model_task(self):
        logger.info("🔄 Запуск обновления модели...")
        try:
            df = load_matches_data(self.config.data_path)
            if df is None:
                logger.error("❌ Не удалось загрузить данные")
                return
            model_data = train_models(df)
            if model_data and save_model(model_data, self.config.model_path):
                logger.info(f"✅ Модель обновлена! Матчей: {len(df)}")
        except Exception as e:
            logger.error(f"❌ Ошибка обновления: {e}")
    
    def start(self):
        self.scheduler.add_job(
            self.update_model_task,
            CronTrigger(day_of_week='sun', hour=3, minute=0),
            id='weekly_model_update'
        )
        self.scheduler.start()
        logger.info("⏰ Планировщик запущен")
    
    def stop(self):
        self.scheduler.shutdown()
        logger.info("⏹️ Планировщик остановлен")