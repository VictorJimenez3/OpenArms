import os
import uvicorn
if __name__=='__main__':
    uvicorn.run('agentic.openarms_lab.app:app',host=os.getenv('OPENARMS_HOST','127.0.0.1'),port=int(os.getenv('PORT','8000')),workers=1)
