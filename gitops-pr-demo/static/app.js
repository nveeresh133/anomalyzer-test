const recommendations = [

{
    resource_name:"storage-prod",
    resource_type:"ObjectBucket",
    icon:"🪣",
    file_path:"claims/storage.yaml",
    field:"tier",
    current_value:"cool",
    recommended_value:"hot",
    estimated_savings:"£120/month"
},

{
    resource_name:"storage-prod",
    resource_type:"ObjectBucket",
    icon:"🪣",
    file_path:"claims/storage.yaml",
    field:"lifecycleDays",
    current_value: "90",
    recommended_value: "60",
    estimated_savings:"£110/month"
},

{
    resource_name:"aks-prod",
    resource_type:"KubernetesCluster",
    icon:"☸️",
    file_path:"claims/aks-cluster.yaml",
    field:"vmSize",
    current_value:"Standard_D8s_v3",
    recommended_value:"Standard_D4s_v3",
    estimated_savings:"£350/month"
},

{
    resource_name:"postgres-prod",
    resource_type:"PostgreSQL",
    icon:"🐘",
    file_path:"claims/postgresql.yaml",
    field:"sku",
    current_value:"Standard_D4s_v3",
    recommended_value:"Standard_D2s_v3",
    estimated_savings:"£250/month"
}

];

const container=document.querySelector(".placeholder");

container.innerHTML="";

recommendations.forEach(rec=>{

container.innerHTML+=`

<div class="recommendation-card">

<div class="card-header">

<div>

<h4>${rec.icon} ${rec.resource_type}</h4>

<p>${rec.resource_name}</p>

</div>

<div class="saving">

${rec.estimated_savings}

</div>

</div>

<div class="card-body-custom">

<div>

<b>Current</b>

<p>${rec.current_value}</p>

</div>

<div>

<b>Recommended</b>

<p>${rec.recommended_value}</p>

</div>

<div>

<b>Field</b>

<p>${rec.field}</p>

</div>

</div>

<div class="card-footer-custom">

<button
class="apply-btn"
onclick="applyRecommendation(${recommendations.indexOf(rec)})">

Apply Recommendation

</button>

</div>

</div>

`;

});

async function applyRecommendation(index){

    const recommendation = recommendations[index];

    const button = event.target;

    button.disabled = true;
    button.innerHTML = "Applying...";

    try{

        const response = await fetch("/recommendation/apply",{

            method:"POST",

            headers:{
                "Content-Type":"application/json"
            },

            body:JSON.stringify({

                resource_name:recommendation.resource_name,
                resource_type:recommendation.resource_type,
                file_path:recommendation.file_path,
                field:recommendation.field,
                current_value:recommendation.current_value,
                recommended_value:recommendation.recommended_value,
                estimated_savings:recommendation.estimated_savings

            })

        });

        const result = await response.json();

        showSuccess(result);

        button.innerHTML="✔ Applied";
        button.style.background="#18b56f";

    }
    catch(err){

        console.log(err);

        button.innerHTML="Failed";
        button.style.background="#dc3545";

    }

}

function showSuccess(result){

    const popup=document.createElement("div");

    popup.className="success-popup";

    popup.innerHTML=`

        <h3>✅ Recommendation Applied</h3>

        <br>

        <b>Status</b>

        <p>${result.status}</p>

        <br>

        <b>Branch</b>

        <p>${result.branch}</p>

        <br>

        <b>Pull Request</b>

        <p>

            <a href="${result.pull_request.url}"
               target="_blank">

                ${result.pull_request.url}

            </a>

        </p>

    `;

    document.body.appendChild(popup);

    setTimeout(()=>{

        popup.remove();

    },5000);

}

loadSidePanels();

async function loadSidePanels(){

    const response = await fetch("/github/pullrequests");

    const prs = await response.json();

    const prContainer = document.getElementById("prList");

    prContainer.innerHTML = "";

    if(prs.length===0){

        prContainer.innerHTML="<p>No Open Pull Requests</p>";

        return;
    }

    prs.forEach(pr=>{

        prContainer.innerHTML += `

        <div class="pr-item">

            <div class="pr-title">

                PR #${pr.number}

            </div>

            <div>

                ${pr.title}

            </div>

            <small>

                ${pr.branch}

            </small>

            <br>

            <a href="${pr.url}" target="_blank">

                Open in GitHub

            </a>

        </div>

        `;

    });

}

loadSidePanels();

setInterval(loadSidePanels,10000);




// function loadSidePanels(){

//     const prContainer=document.getElementById("prList");

//     prContainer.innerHTML=`

//         <div class="pr-item">

//             <div class="pr-title">

//                 🪣 Storage

//             </div>

//             <div class="pr-status">

//                 PR #12 • Open

//             </div>

//         </div>

//         <div class="pr-item">

//             <div class="pr-title">

//                 ☸️ AKS

//             </div>

//             <div class="pr-status">

//                 PR #13 • Open

//             </div>

//         </div>

//     `;

//     const activity=document.getElementById("activityList");

//     activity.innerHTML=`

//         <div class="activity">

//             ✔ Storage Tier updated

//         </div>

//         <div class="activity">

//             ✔ Storage Versioning updated

//         </div>

//         <div class="activity">

//             ✔ AKS VM resized

//         </div>

//         <div class="activity">

//             ✔ PostgreSQL SKU changed

//         </div>

//     `;

// }