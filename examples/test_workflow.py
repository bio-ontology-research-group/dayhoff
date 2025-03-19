from dayhoff.workflows import Workflow, WorkflowStep, CWLGenerator, NextflowGenerator

def test_workflow():
    print("Testing workflow generation...\n")
    
    # Create a simple workflow
    workflow = Workflow("test_workflow")
    
    # Add steps
    step1 = WorkflowStep(
        name="step1",
        tool="fastqc",
        inputs={"input_file": "File"},
        outputs={"output_html": "File"},
        container="quay.io/biocontainers/fastqc:0.11.9--0",
        requirements=[]
    )
    
    step2 = WorkflowStep(
        name="step2",
        tool="multiqc",
        inputs={"input_dir": "Directory"},
        outputs={"report_html": "File"},
        container="quay.io/biocontainers/multiqc:1.11--pyhdfd78af_0",
        requirements=[]
    )
    
    workflow.add_step(step1)
    workflow.add_step(step2, depends_on=["step1"])
    
    # Generate CWL
    cwl_gen = CWLGenerator()
    cwl = cwl_gen.generate(workflow)
    print("Generated CWL:")
    print(cwl)
    
    # Generate Nextflow
    nf_gen = NextflowGenerator()
    nf = nf_gen.generate(workflow)
    print("\nGenerated Nextflow:")
    print(nf)
    
    print("\nWorkflow test completed successfully!")

if __name__ == "__main__":
    test_workflow()
