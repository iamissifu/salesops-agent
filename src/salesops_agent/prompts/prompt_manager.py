from pathlib import Path
import yaml
from typing import Dict, Any, Optional

class PromptManager:
    def __init__(self, prompts_dir: Path = Path(__file__).parent / "versioned"):
        self.prompts_dir = prompts_dir
        self.current_version = "v1"
        
    def get_system_prompt(self, version: Optional[str] = None) -> str:
        version = version or self.current_version
        prompt_file = self.prompts_dir / f"system_prompt_{version}.yaml"
        
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        
        with open(prompt_file, 'r') as f:
            prompt_data = yaml.safe_load(f)
        
        return prompt_data['content']
    
    def get_prompt_version(self) -> Dict[str, Any]:
        prompt_file = self.prompts_dir / f"system_prompt_{self.current_version}.yaml"
        with open(prompt_file, 'r') as f:
            return yaml.safe_load(f)