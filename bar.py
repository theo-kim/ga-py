from progress.bar import Bar

class RunnerProgress(Bar) :
    suffix = "%(phase)s | Generation: %(current_generation)d | Fitness: %(prev_score).2f | Avg: %(avg)ds"

    def __init__(self, *args, **kwargs) :
        super().__init__(*args, **kwargs)
        self.prev_score : int = 0
        self.current_generation : int = 0

    def next_generation(self, generation: int) :
        self.current_generation = generation
        self.phase = f"Testing"
        self.next()

    def perform_selection(self, avg_score: float) :
        self.prev_score = avg_score
        self.phase = f"Selection"
        self.update()

    def perform_reproduction(self) :
        self.phase = f"Reproduction"
        self.update()
